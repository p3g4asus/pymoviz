import traceback
from os.path import join

from kivy.core.clipboard import Clipboard
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen
from kivymd.toast.kivytoast.kivytoast import toast
from util import db_dir, init_logger

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
            left_action_items: [["arrow-left", lambda x: root.stop_querying(back=True)]]
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
        self.query_state = -1
        self.query_text = ''
        self.result_text = ''

    def get_query(self, txt):
        if txt.find('$limit') != -1:
            self.query_state = self.query_state + 1
            txt = txt.replace('$limit', f'1 offset {self.query_state}')
        else:
            self.query_state = -2
        return txt

    def start_querying(self):
        self.query_state = -1
        self.result_text = ''
        self.query_text = self.ids.id_query.text
        self.dispatch_on_query(self.get_query(self.query_text))

    def stop_querying(self, back=False):
        is_querying = self.query_state != -1
        self.ids.id_result.text = self.result_text
        self.query_state = -1
        self.result_text = ''
        self.query_text = ''
        self.ids.id_query.readonly = False
        if self.ids.id_query.error:
            self.ids.id_toolbar.right_action_items = []
        else:
            self.ids.id_toolbar.right_action_items = [
                ["floppy", lambda x: self.start_querying()],
            ]
        self.dispatch_on_query(None if back else '', is_querying)

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
                ["floppy", lambda x: self.start_querying()],
            ]
        else:
            self.ids.id_toolbar.right_action_items = []

    def on_query(self, query):
        _LOGGER.info(f"On query called {query}")

    def format_result(self, result):
        txt2 = ''
        txt = ''
        if result['error']:
            txt = result['error'] + '\n'
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
            if len(result["rows"]):
                txt2 = ('\n'.join(result['rows'])) + '\n'
            if len(result['rows']) > 100:
                txt += ('\n'.join(result['rows'][0:100])) + '\n...\n'
            else:
                txt += txt2 + '\n'
        return (txt, txt2)

    def set_result(self, results):
        txt = self.result_text
        complete_all = ''
        next_query = False
        _LOGGER.info(f'Query results arrived')
        _LOGGER.debug(f'Query results {results}')
        for i, result in enumerate(results):
            if self.query_state >= 0 and 'rows' in result and not result['rows']:
                break
            elif 'cols' in result and ['__file__'] == result['cols'] and len(results) > i + 1:
                if result['rows']:
                    next_query = self.query_state >= 0
                    fname = join(db_dir('sessions'), result['rows'][0])
                    try:
                        with open(fname, 'w') as out_file:
                            for k in range(i + 1, len(results)):
                                r = results[k]
                                if r['cols'] and r['rows']:
                                    out_file.write(("\t".join(r["cols"])) + '\n')
                                    out_file.write(("\n".join(r["rows"])) + '\n')
                                else:
                                    label, complete = self.format_result(r)
                                    txt += label
                        txt += f'File {fname} written OK\n'
                    except Exception as ex:
                        txt += f'{ex.__class__.__name__}: File name: {fname} -> {ex}\n'
                break
            else:
                label, complete = self.format_result(result)
                txt += label
                if complete:
                    complete_all += complete
        if complete_all:
            try:
                Clipboard.copy(complete_all)
                toast('Query result rows have been copied to clipboard')
            except Exception:
                _LOGGER.error(f'Copy Exception {traceback.format_exc()}')
        self.ids.id_result.text = self.result_text = txt
        if next_query:
            self.dispatch_on_query(self.get_query(self.query_text))
        else:
            self.ids.id_query.readonly = False
            self.ids.id_toolbar.right_action_items = [
                ["floppy", lambda x: self.start_querying()],
            ]

    def on_result(self, ti, txt, *args):
        width_calc = self.ids.scrlv.width
        width_calc = max(width_calc, ti._get_text_width(txt,
                                                        ti.tab_width,
                                                        ti._label_cached) + 20)
        ti.width = width_calc

    def dispatch_on_query(self, query, is_querying=False):
        if not query:
            if query is None:
                self.manager.remove_widget(self)
            query = '' if is_querying else None
        elif query:
            self.ids.id_result.text = 'Querying...\n' + self.result_text
            self.ids.id_query.readonly = True
            self.ids.id_toolbar.right_action_items = [
                ["stop", lambda x: self.stop_querying()],
            ]
        self.dispatch("on_query", query)
