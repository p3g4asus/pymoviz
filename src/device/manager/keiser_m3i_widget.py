from kivy.lang import Builder
from device.manager.widget import ConfWidget


Builder.load_string(
    '''
<KeiserM3iConfWidget>:
    orientation: 'vertical'
    GridLayout:
        cols: 2
        rows: 2
        padding: [dp(30), dp(20)]
        MDLabel:
            text: 'Machine ID'
        MDSlider:
            id: id_machine
            min: 1
            max: 254
            value: root.DEFAULT_MACHINE
        MDLabel:
            text: 'Buffer distanza'
        MDSlider:
            id: id_buffer
            min: 1
            max: 1000
            value: root.DEFAULT_BUFFER
    '''
)


class KeiserM3iConfWidget(ConfWidget):
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
