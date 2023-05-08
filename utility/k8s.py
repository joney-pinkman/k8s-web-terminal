# -*- coding=utf-8 -*-
# Copyright 2018 Alex Ma

"""
:author Alex Ma
:date 2018/10/15 

"""
import json
import os
import threading
from utility.log import log
from kubernetes import client, config
from kubernetes.stream import stream
from kubernetes.stream.ws_client import RESIZE_CHANNEL

# from kubernetes.client import *
# from kubernetes.client.rest import ApiException


class KubernetesAPI(object):

    def __init__(self, api_host, ssl_ca_cert, key_file, cert_file):
        config.load_kube_config()
        # kub_conf = client.Configuration()
        # kub_conf.host = api_host
        # kub_conf.ssl_ca_cert = ssl_ca_cert
        # kub_conf.cert_file = cert_file
        # kub_conf.key_file = key_file

        self.api_client = client.ApiClient()
        self.client_core_v1 = client.CoreV1Api(api_client=self.api_client)
        self.client_apps_v1 = client.AppsV1Api(api_client=self.api_client)
        self.client_extensions_v1 = client.ExtensionsV1beta1Api(
            api_client=self.api_client)

        self.api_dict = {}

    def __getattr__(self, item):
        if item in self.api_dict:
            return self.api_dict[item]
        if hasattr(client, item) and callable(getattr(client, item)):
            self.api_dict[item] = getattr(client, item)(
                api_client=self.api_client)
            return self.api_dict[item]


class K8SClient(KubernetesAPI):

    def __init__(self, api_host, ssl_ca_cert, key_file, cert_file):
        super(K8SClient, self).__init__(
            api_host, ssl_ca_cert, key_file, cert_file)

    @staticmethod
    def gen_ca():
        ssl_ca_cert = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            '_credentials/kubernetes_dev_ca_cert')
        key_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            '_credentials/kubernetes_dev_key')
        cert_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            '_credentials/kubernetes_dev_cert')

        return ssl_ca_cert, key_file, cert_file

    def terminal_start(self, namespace, pod_name, container):
        command = [
            "/bin/sh",
            "-c",
            'TERM=xterm-256color; export TERM; [ -x /bin/bash ] '
            '&& ([ -x /usr/bin/script ] '
            '&& /usr/bin/script -q -c "/bin/bash" /dev/null || exec /bin/bash) '
            '|| exec /bin/sh']

        container_stream = stream(
            self.client_core_v1.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=namespace,
            container=container,
            command=command,
            stderr=True, stdin=True,
            stdout=True, tty=True,
            _preload_content=False
        )
        # container_stream.write_channel(RESIZE_CHANNEL, json.dumps({"Height": int(rows), "Width": int(cols)}))

        return container_stream


class K8SStreamThread(threading.Thread):

    def __init__(self, ws, container_stream):
        super(K8SStreamThread, self).__init__()
        self.ws = ws
        self.stream = container_stream

    def run(self):
        while self.stream.is_open():
            try:
                self.stream.update(timeout=1)
                if self.stream.peek_stdout():
                    stdout = self.stream.read_stdout()
                    self.ws.send(stdout)

                if self.stream.peek_stderr():
                    stderr = self.stream.read_stderr()
                    self.ws.send(stderr)
            except Exception as err:
                log.error('container stream err: {}'.format(err))
                pass
        else:
            self._disconnect()
    
    def _disconnect(self):
        try:
            log.info('container stream closed')
            if self.stream.is_open():
                self.stream.write_stdin('\u0003')
                self.stream.write_stdin('\u0004')
                self.stream.write_stdin('exit\r')

            self.ws.close()
        except:
            pass