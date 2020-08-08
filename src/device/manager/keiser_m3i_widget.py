from kivy.lang import Builder
from kivy.uix.gridlayout import GridLayout
from device.manager.widget import ConfWidget


Builder.load_string(
    '''
<KeiserM3iConfWidget>:
    cols: 2
    rows: 2
    padding: [dp(30), dp(20)]
    height: self.minimum_height
    MDLabel:
        size_hint_x: 0.4
        text: 'Machine ID'
        size_hint_y: None
        height: dp(70)
    MDSlider:
        size_hint_x: 0.6
        id: id_machine
        min: 1
        max: 254
        value: root.DEFAULT_MACHINE
        size_hint_y: None
        height: dp(70)
    MDLabel:
        size_hint_x: 0.4
        text: 'Buffer distanza'
        size_hint_y: None
        height: dp(70)
    MDSlider:
        size_hint_x: 0.6
        id: id_buffer
        min: 1
        max: 1000
        value: root.DEFAULT_BUFFER
        size_hint_y: None
        height: dp(70)
    '''
)


class KeiserM3iConfWidget(GridLayout, ConfWidget):
    DEFAULT_BUFFER = 150
    DEFAULT_MACHINE = 99

    def __init__(self, *args, **kwargs):
        super(KeiserM3iConfWidget, self).__init__(*args, **kwargs)

    def is_ok(self):
        return True

    def clear(self):
        self.ids.id_buffer.value = KeiserM3iConfWidget.DEFAULT_BUFFER
        self.ids.id_machine.value = KeiserM3iConfWidget.DEFAULT_MACHINE

    def conf2gui(self, conf):
        if 'buffer' in self.conf:
            self.ids.id_buffer.value = self.conf['buffer']
        if 'machine' in self.conf:
            self.ids.id_machine.value = self.conf['machine']

    def gui2conf(self):
        self.conf = dict(
            buffer=int(self.ids.id_buffer.value),
            machine=int(self.ids.id_machine.value))
        return self.conf
