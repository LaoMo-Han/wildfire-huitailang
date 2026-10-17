# -*- coding: utf-8 -*-
"""UI only: HTTPS and installation are owned by the C# launcher."""
import json
import os
import time
import BigWorld
import rc
from guis import xnui, font, color, guiManager, SysBox

def gb(text):
    return text.encode('gbk', 'replace')

class Updates(object):
    def __init__(self, runtime):
        self.runtime = runtime
        self.data = {}
        self.pending_check = None
        # Keep all updater UI inside the native settings window. Its parent
        # hides immediately when settings close, even before the next poll.
        self.panel = xnui.XDialog(runtime.settings.ui, 205, 466, rc.COMMON_BG_DUMMY)
        self.panel.set_size(410, 77)
        self.label = xnui.XLabel(self.panel, 0, 0, gb(u'\u5355\u673a\u7248'), font.TEXT_12, color.WATER_BLUE)
        self.button = xnui.XButton(self.panel, 0, 25, rc.COMMON_BTN_RECT_BIG, gb(u'\u68c0\u67e5\u66f4\u65b0'))
        self.button.set_size(150, 44)
        self.feedback = xnui.XButton(self.panel, 162, 25, rc.COMMON_BTN_RECT_BIG, gb(u'\u53cd\u9988 Bug'))
        self.feedback.set_size(150, 44)
        self.button.event_click = lambda sender: self.clicked()
        self.feedback.event_click = lambda sender: self.request('feedback')
        guiManager.instance().elements['offline_updates'] = self.panel
        self.panel.visible = bool(runtime.settings.ui.visible)
        BigWorld.callback(0.5, self.tick)

    def request(self, action):
        path = '../game/update_request.json'
        temporary = path+'.new'
        request_id = str(time.time())+'-'+action
        with open(temporary,'w') as stream:
            json.dump({'id':request_id,'action':action},stream)
        if os.path.exists(path):
            os.remove(path)
        os.rename(temporary,path)
        return request_id

    def show(self):
        if SysBox.instance().show_array:
            return
        state = self.data.get('state')
        if state == 'available':
            text = u'\u65b0\u7248\u672c '+self.data.get('version','')+u'\n'+self.data.get('notes','')[:1600]+u'\n\n\u4e0b\u8f7d\u66f4\u65b0\uff1f'
            SysBox.double_btn(text=gb(text),yes_callback=lambda: self.request('download'),cancel_key='ESC')
        elif state == 'ready':
            SysBox.double_btn(text=gb(u'\u66f4\u65b0\u5df2\u4e0b\u8f7d\u3002\u9000\u51fa\u6e38\u620f\u5e76\u5b89\u88c5\u540e\u91cd\u542f\uff1f'),yes_callback=self.install,cancel_key='ESC')
        elif state == 'downloading':
            SysBox.double_btn(text=gb(u'\u6b63\u5728\u4e0b\u8f7d\uff0c\u662f\u5426\u53d6\u6d88\uff1f'),yes_callback=lambda: self.request('cancel'),cancel_key='ESC')
        else:
            SysBox.double_btn(text=gb(self.data.get('message',u'\u68c0\u67e5\u66f4\u65b0\u540e\u53ef\u4e0b\u8f7d\u6700\u65b0\u8865\u4e01')),cancel_key='ESC')

    def clicked(self):
        if self.data.get('state') in ('available','ready','downloading'):
            self.show()
        else:
            self.pending_check = self.request('check')

    def install(self):
        self.request('install')
        # Give the launcher's 500 ms request poll time to record restart intent.
        BigWorld.callback(1.0, BigWorld.quit)

    def tick(self):
        try:
            with open('../game/update_status.json') as stream:
                self.data = json.load(stream)
            state = self.data.get('state')
            label = u'\u5355\u673a\u7248 '+self.data.get('current_version',self.data.get('version',''))
            if state in ('available','downloading','ready'):
                label += u' \u2192 '+self.data.get('version','')
            self.label.text = gb(label)
            text = {'available':u'\u6709\u65b0\u7248\u672c','ready':u'\u9000\u51fa\u5e76\u66f4\u65b0','checking':u'\u6b63\u5728\u68c0\u67e5'}.get(state,u'\u68c0\u67e5\u66f4\u65b0')
            if state == 'downloading':
                text = u'\u4e0b\u8f7d '+str(self.data.get('progress',0))+'%'
            self.button.text = gb(text)
            if self.pending_check and self.pending_check == self.data.get('request_id') and state not in ('checking','downloading'):
                self.pending_check = None
                if state in ('available', 'ready') and self.runtime.settings.ui.visible:
                    self.show()
        except (IOError,ValueError):
            pass
        self.panel.visible = bool(self.runtime.settings.ui.visible)
        BigWorld.callback(0.5,self.tick)

def install(runtime):
    return Updates(runtime)
