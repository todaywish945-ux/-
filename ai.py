# -*- coding: utf-8 -*-
"""AI 聊天逻辑：后台请求线程 + 消息历史裁剪"""
import json
import urllib.request
from PyQt6.QtCore import QThread, pyqtSignal


def trim_history(history, max_history):
    """保留首条 system 消息 + 最近 max_history 条对话消息"""
    if not history:
        return history
    return [history[0]] + history[1:][-max_history:]


class AIWorker(QThread):
    """后台线程调用 OpenAI 兼容 /chat/completions，避免阻塞界面"""
    finished = pyqtSignal(str, str)

    def __init__(self, base_url, api_key, model, messages, parent=None):
        super().__init__(parent)
        self._url = base_url.rstrip('/') + '/chat/completions'
        self._api_key = api_key
        self._model = model
        self._messages = messages

    def run(self):
        try:
            payload = json.dumps({
                'model': self._model,
                'messages': self._messages,
                'stream': False,
            }).encode('utf-8')
            req = urllib.request.Request(self._url, data=payload, method='POST')
            req.add_header('Content-Type', 'application/json')
            if self._api_key:
                req.add_header('Authorization', 'Bearer ' + self._api_key)
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            content = data['choices'][0]['message']['content']
            self.finished.emit(content, '')
        except Exception as e:
            self.finished.emit('', '{}'.format(e))
