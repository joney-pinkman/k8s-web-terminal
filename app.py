# -*- coding=utf-8 -*-
# Copyright 2018 Alex Ma

"""
:author Alex Ma
:date 2018/10/15

"""
from werkzeug import serving
from flask_sockets import Sockets
from flask import Flask, render_template
from utility.log import log
from utility.k8s import K8SClient, K8SStreamThread
from kubernetes.stream.ws_client import RESIZE_CHANNEL

import json

app = Flask(__name__, static_folder='static',
            static_url_path='/terminal/static')
sockets = Sockets(app)


@app.route('/terminal/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/terminal/window', methods=['GET'])
def terminal():
    return render_template('terminal.html')

@app.route('/terminal/new_window', methods=['GET'])
def new_terminal():
    return render_template('new_terminal.html')


RESIZE_KEYWORD = '__resize__'
@sockets.route('/terminal/<namespace>/<pod>/<container>')
def terminal_socket(ws, namespace, pod, container):
    log.info('Try create socket connection')
    ssl_ca_cert, key_file, cert_file = K8SClient.gen_ca()
    kub = K8SClient(
        api_host='kubernetes_api_url',
        ssl_ca_cert=ssl_ca_cert,
        key_file=key_file,
        cert_file=cert_file)

    try:
        container_stream = kub.terminal_start(namespace, pod, container)
    except Exception as err:
        log.error('Connect container error: {}'.format(err))
        ws.close()
        return

    kub_stream = K8SStreamThread(ws, container_stream)
    kub_stream.start()

    log.info('Start terminal')
    try:
        while (not ws.closed) and container_stream.is_open():
            message = ws.receive()
            if message is not None:
                if message.startswith(RESIZE_KEYWORD):
                    info = message[len(RESIZE_KEYWORD):]
                    try:
                        information = json.loads(info)
                        cols = information['cols']
                        rows = information['rows']
                        log.info('resize cols[%s] rows[%s]' % (cols, rows))
                        container_stream.write_channel(RESIZE_CHANNEL, json.dumps({"Height": rows, "Width": cols}))

                    except:
                        pass
                elif message != '__ping__':
                    container_stream.write_stdin(message)
    except Exception as err:
        log.error('Connect container error: {}'.format(err))
    finally:
        kub_stream._disconnect()


@serving.run_with_reloader
def run_server():
    app.debug = True
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler
    server = pywsgi.WSGIServer(
        listener = ('0.0.0.0', 8100),
        application=app,
        handler_class=WebSocketHandler)
    server.serve_forever()


if __name__ == '__main__':
    run_server()
