from kivy.core.clipboard import Clipboard
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen
from kivymd.toast.kivytoast.kivytoast import toast
from util import init_logger

import traceback


_LOGGER = init_logger(__name__)

Builder.load_string(
    '''
<QueryWidget>:
    name: 'query'
    GridLayout:
        spacing: dp(5)
        height: self.minimum_height
        rows: 3
        cols: 1
        MDToolbar:
            id: id_toolbar
            pos_hint: {'top': 1}
            size_hint: (1, 0.1)
            title: 'Execute Query'
            md_bg_color: app.theme_cls.primary_color
            left_action_items: [["arrow-left", lambda x: root.dispatch_on_query(None)]]
            elevation: 10
        MDTextField:
            id: id_query
            size_hint: (1, 0.45)
            multiline: True
            write_tabs: False
            helper_text_mode: "on_error"
            helper_text: "Enter a query"
            on_text: root.enable_buttons(self, self.text)
        ScrollView:
            id: scrlv
            size_hint: (1, 0.45)
            MDTextField:
                id: id_result
                size_hint: None, None
                multiline: True
                write_tab: True
                readonly: True
                on_text: root.on_result(self, self.text)
                height: max(self.minimum_height, scrlv.height)
    '''
)


class QueryWidget(Screen):

    def __init__(self, **kwargs):
        self.register_event_type('on_query')
        super(QueryWidget, self).__init__(**kwargs)

    def enable_buttons(self, inst, text, *args, **kwargs):
        dis = not text
        if inst.error and not dis:
            inst.error = False
            inst.on_text(inst, text)
        elif not inst.error and dis:
            inst.error = True
            inst.on_text(inst, text)
        if not dis:
            self.ids.id_toolbar.right_action_items = [
                ["floppy", lambda x: self.dispatch_on_query(self.ids.id_query.text)],
            ]
        else:
            self.ids.id_toolbar.right_action_items = []

    def on_query(self, query):
        _LOGGER.info(f"On query called {query}")

    def set_result(self, result):
        if result['error']:
            txt = result['error']
        else:
            if result['lastrowid'] > 0:
                txt = f'id: {result["lastrowid"]}\n'
            else:
                txt = ''
            if result['rowcount'] >= 0:
                txt += f'Row changes: {result["rowcount"]}\n'
            txt += f'DB changes before/after: {result["changes_before"]} / {result["changes_after"]}\n'
            txt += f'Total rows in result: {len(result["rows"])}\n'
            if result['cols']:
                txt += f'cols: %s\n' % ("\t".join(result["cols"]))
            txt2 = '\n'.join(result['rows'])
            if len(result['rows']) > 100:
                txt += ('\n'.join(result['rows'][0:100])) + '...\n'
            else:
                txt += txt2
            if txt2:
                try:
                    Clipboard.copy(txt2)
                    toast('Query result rows have been copied to clipboard')
                except Exception:
                    _LOGGER.error(f'Copy Exception {traceback.format_exc()}')
        self.ids.id_result.text = txt

    def on_result(self, ti, txt, *args):
        width_calc = self.ids.scrlv.width
        width_calc = max(width_calc, ti._get_text_width(txt,
                                                        ti.tab_width,
                                                        ti._label_cached) + 20)
        ti.width = width_calc

    def dispatch_on_query(self, query):
        if not query:
            self.manager.remove_widget(self)
        self.ids.id_result.text = 'Querying...'
        self.dispatch("on_query", query)
