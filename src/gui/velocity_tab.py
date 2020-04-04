import re
import traceback

from kivy.lang import Builder
from kivy.properties import StringProperty, ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.tab import MDTabsBase
from util.velocity_tcp import TcpClient
from util import init_logger

_LOGGER = init_logger(__name__)

Builder.load_string(
    '''
<VelocityTab>:
    orientation: 'vertical'
    ScrollView:
        MDLabel:
            id: id_label
            multiline: True
            markup: True
            size_hint_y: None
            text_size: self.width, None
            height: self.texture_size[1]
    '''
)


class VelocityTab(BoxLayout, MDTabsBase):
    velocity = StringProperty()
    name = StringProperty()
    loop = ObjectProperty(None, allownone=True)
    _template = ObjectProperty(None, allownone=True)
    _STASTR = '_________sta_________'
    _STOSTR = '_________sto_________'

    def __init__(self, **kwargs):
        super(VelocityTab, self).__init__(**kwargs)
        self._template = TcpClient(template_file=self.velocity,
                                   loop=self.loop,
                                   write_out=self.fill_label,
                                   stastr=VelocityTab._STASTR,
                                   stostr=VelocityTab._STOSTR)
        self.text = f'V - {self.name}'

    def fill_label(self, out):
        ttl = self._template.get_var('title')
        if ttl:
            self.text = ttl
        rv = ''
        while True:
            mo = re.search(VelocityTab._STASTR + r'[\n\r]+', out)
            if mo:
                out = out[mo.end():]
            else:
                break
            mo = re.search(VelocityTab._STOSTR + r'[\n\r]+', out)
            if mo:
                rv += out[:mo.start()]
                out = out[mo.end():]
            else:
                break
        if rv:
            try:
                self.ids.id_label.text = rv
            except Exception:
                _LOGGER.error(f'Expansion error: {traceback.format_exc()}')
