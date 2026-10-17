"""Updater UI ownership and silent-check behavior; never contacts the network."""
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch


class Widget:
    def __init__(self,parent,*args):
        self.parent=parent
        self.visible=True
    def set_size(self,*args):pass


class UpdatesTests(unittest.TestCase):
    def setUp(self):
        self.settings=NS(visible=False)
        self.runtime=NS(settings=NS(ui=self.settings))
        self.box=NS(show_array=[],double_btn=Mock())
        mods={'BigWorld':NS(callback=Mock()),'rc':NS(COMMON_BG_DUMMY=0,COMMON_BTN_RECT_BIG=0),
              'guis':NS(xnui=NS(XDialog=Widget,XButton=Widget,XLabel=Widget),
                        font=NS(TEXT_12=0),color=NS(WATER_BLUE=0),SysBox=NS(instance=lambda:self.box,double_btn=self.box.double_btn),
                        guiManager=NS(instance=lambda:NS(elements={}))) }
        self.modules=patch.dict(sys.modules,mods)
        self.modules.start();self.addCleanup(self.modules.stop)
        spec=importlib.util.spec_from_file_location('updates_test',Path(__file__).resolve().parent.parent/'runtime/offline_updates.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.updates=self.module.Updates(self.runtime)

    def tick(self,state,request='manual'):
        data=json.dumps(dict(state=state,request_id=request,current_version='1.0',version='1.1',message='test failure'))
        with patch.object(self.module,'open',return_value=io.StringIO(data),create=True):
            self.updates.tick()

    def test_controls_belong_to_settings_and_start_hidden(self):
        self.assertIs(self.updates.panel.parent,self.settings)
        self.assertFalse(self.updates.panel.visible)

    def test_startup_check_is_silent_for_every_result(self):
        for state in ('checking','current','error','available'):
            with self.subTest(state=state):
                self.tick(state,'startup')
                self.assertFalse(self.updates.panel.visible)
                self.box.double_btn.assert_not_called()

    def test_manual_no_update_and_failure_are_silent(self):
        self.settings.visible=True
        for state in ('current','error'):
            self.updates.pending_check='manual'
            self.tick(state)
            self.assertIsNone(self.updates.pending_check)
            self.box.double_btn.assert_not_called()
        self.assertEqual(self.updates.button.text,'检查更新'.encode('gbk'))

    def test_manual_available_result_can_offer_download_in_settings(self):
        self.settings.visible=True
        self.updates.pending_check='manual'
        self.tick('available')
        self.box.double_btn.assert_called_once()

    def test_late_result_after_closing_settings_never_interrupts_play(self):
        self.updates.pending_check='manual'
        self.tick('available')
        self.box.double_btn.assert_not_called()
        self.assertFalse(self.updates.panel.visible)

    def test_only_matching_request_completes_manual_check(self):
        self.settings.visible=True
        self.updates.pending_check='new'
        self.tick('available','old')
        self.assertEqual(self.updates.pending_check,'new')
        self.box.double_btn.assert_not_called()

    def test_corrupt_status_does_not_show_popup_or_escape_settings(self):
        with patch.object(self.module,'open',return_value=io.StringIO('invalid'),create=True):
            self.updates.tick()
        self.assertFalse(self.updates.panel.visible)
        self.box.double_btn.assert_not_called()


if __name__=='__main__':unittest.main()
