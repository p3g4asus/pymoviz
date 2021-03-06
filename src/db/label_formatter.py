import abc
import re
from datetime import datetime

from db import SerializableDBObj
from util.const import (DEVSTATE_CONNECTED, DEVSTATE_CONNECTING,
                        DEVSTATE_DISCONNECTED, DEVSTATE_DISCONNECTING,
                        DEVSTATE_DPAUSE, DEVSTATE_IDLE, DEVSTATE_INVALIDSTEP,
                        DEVSTATE_ONLINE, DEVSTATE_SEARCHING, DEVSTATE_UNINIT)
from util import init_logger

_LOGGER = init_logger(__name__)


class SetColor(object):
    def __init__(self, name, field_name, method_name):
        self.name = name
        self.field_name = field_name
        self.method_name = method_name

    def get(self, obj):
        # col = getattr(obj, self.field_name)
        # return '#ffffff' if not col or col[0] != '#' else col
        return getattr(obj, self.field_name)

    def _set(self, obj, val):
        setmethod = getattr(obj, self.method_name)
        setmethod(val)

    def set(self, obj, val):
        if self.field_name in obj.settings:
            obj.settings[self.field_name] = val
        self._set(obj, val)


_SETCOLOR_BACKGROUND = SetColor('Background', 'background', 'set_background')
_SETCOLOR_MAIN = SetColor('Main', 'col', '_set_col')
_SETCOLOR_ERROR = SetColor('Error', 'colerror', '_set_colerror')
_SETCOLOR_WARNING = SetColor('Warning', 'colmin', '_set_colmin')
_SETCOLOR_OK = SetColor('OK', 'colmax', '_set_colmax')


class LabelFormatter(SerializableDBObj, abc.ABC):
    __table__ = 'label'
    __columns__ = (
        '_id',
        'view',
        'name',
        'device',
        'example_conf',
        'pre',
        'classname',
        'settings',
        'background',
        'timeout',
        'timeouttime',
        'orderd',
        'type',
    )
    __columns2field__ = {
        'orderd': 'order'
    }

    __load_order__ = {'orderd': 'asc'}

    __update_columns__ = (
        'device',
        'settings',
        'background',
        'orderd',
    )

    __create_table_query__ =\
        '''
        create table if not exists label
            (_id integer primary key,
            view integer not null,
            name text not null,
            device integer,
            example_conf text not null,
            pre text,
            classname text not null,
            settings text default '{}',
            timeout text,
            timeouttime integer default 7,
            background text,
            type text not null,
            orderd integer not null,
            FOREIGN KEY(view) REFERENCES view(_id) ON DELETE CASCADE,
            FOREIGN KEY(device) REFERENCES device(_id) ON DELETE CASCADE);
        '''

    def __init__(self,
                 name='',
                 example_conf=(),
                 pre='$D: ',
                 timeout='---',
                 timeouttime=7,
                 type='fitobj',
                 colerror='#f44336',
                 col='#212121',
                 **kwargs):
        super(LabelFormatter, self).__init__(name=name,
                                             example_conf=example_conf,
                                             pre=pre,
                                             type=type,
                                             timeouttime=timeouttime,
                                             timeout=timeout,
                                             colerror=colerror,
                                             col=col,
                                             **kwargs)
        self.deviceobj = self.f('deviceobj')
        if self.classname is None:
            self.classname = self.fullname()
        self.wrappers = []

    def _set_colerror(self, colerror):
        self._set_setting_field(colerror=colerror)

    def _set_col(self, col):
        self._set_setting_field(col=col)

    @classmethod
    def get_colors_to_set(cls):
        return dict(Background=_SETCOLOR_BACKGROUND, Error=_SETCOLOR_ERROR, Main=_SETCOLOR_MAIN)

    def __lt__(self, other):
        return self.orderd < other.orderd

    def __le__(self, other):
        return self.orderd <= other.orderd

    def __gt__(self, other):
        return self.orderd > other.orderd

    def __ge__(self, other):
        return self.orderd >= other.orderd

    def _set_settings(self, settings):
        if settings:
            for key, val in settings.items():
                setattr(self, key, val)
        self.settings = settings

    def add_wrapper(self, tag, val, flag, pre='', post=''):
        if tag:
            mo = re.search(r'^<([a-z0-9\-_]+)', tag)
            tagend = f'</{mo.group(1)}>' if mo else f'[/{tag}]'
        else:
            tagend = ''
        self.wrappers.append(dict(tag=tag, tagend=tagend, val=val, flag=flag, pre=pre, post=post))
        return self

    def wrap(self, stringtowrap, idxtowrap, pref='norm'):
        sret = ''
        flagtowrap = 1 << idxtowrap
        for w in self.wrappers:
            if w["flag"] & flagtowrap:
                tag = w["tag"]
                if tag:
                    val = w["val"]
                    if val is None or isinstance(val, str):
                        sval = '' if val is None or val == '' else f'={val}'
                        sret += f'[{tag}{sval}]'
                    elif isinstance(val, dict):
                        for repid, repstr in val.items():
                            if not pref or repid.startswith(pref):
                                repid = repid[len(pref):]
                                tag = tag.replace(f'%{repid}%', repstr)
                        sret += tag
                sret += w["pre"]
        sret += stringtowrap
        for w in reversed(self.wrappers):
            if w["flag"] & flagtowrap:
                sret += (w["post"] + w["tagend"])
        return sret

    def change_fields(self, *args, **kwargs):
        if args:
            kwargs = args[0]
        for key, val in kwargs.items():
            if key in self.settings:
                setattr(self, key, val)
                self.settings[key] = val
            else:
                try:
                    self.__getitem__(key)
                    self.s(key, val)
                except Exception:
                    pass

    def _set_setting_field(self, **kwargs):
        try:
            getattr(self, 'settings')
        except AttributeError:
            self.settings = dict()
        if self.settings is None:
            self.settings = dict()
        for key, val in kwargs.items():
            if key in self.settings:
                setattr(self, key, self.settings[key])
            else:
                setattr(self, key, val)
                self.settings[key] = val

    @abc.abstractmethod
    def format(self, *args, **kwargs):
        pass

    @staticmethod
    def wrap_color(txt, col='#fdd835'):
        return f'[color={col}]{txt}[/color]'

    def set_timeout(self):
        if self.col and self.colerror:
            return self.wrap(f'[color={self.col}]{self.get_pre()}[/color]', 0) +\
                self.wrap(f'[color={self.colerror}]{self.timeout}[/color]', 5, pref='error')
        else:
            return self.wrap(self.get_pre(), 0) + self.wrap(self.timeout, 5, pref='error')

    def reset(self):
        self.order = None
        self.background = None

    def print_example(self):
        if isinstance(self.example_conf, (tuple, list)):
            return self.format(*tuple(self.example_conf))
        else:
            return self.format(self.example_conf)

    def get_title(self):
        return (self.deviceobj.get_alias() if self.deviceobj else 'None') + " " + self.name

    def get_pre(self):
        return self.pre.replace('$D', self.deviceobj.get_alias() if self.deviceobj else 'None')

    def set_device(self, deviceobj):
        self.deviceobj = deviceobj
        self.device = deviceobj.get_id()

    def set_background(self, background):
        self.background = background

    def set_order(self, order):
        self.order = order

    @staticmethod
    def get_fields(fldnamelst, obj):
        if not isinstance(obj, object) or obj is not None:
            rv = []
            _LOGGER.debug(f'flds={fldnamelst} obj={obj}')
            for i in fldnamelst:
                extract_time = False
                if i.startswith('%t'):
                    extract_time = True
                    i = i[2:]
                if i in obj:
                    if extract_time:
                        tm = obj[i]
                        hrs = tm // 3600
                        tm -= hrs * 3600
                        mins = tm // 60
                        tm -= mins * 60
                        secs = tm % 60
                        rv.append(hrs)
                        rv.append(mins)
                        rv.append(secs)
                    else:
                        rv.append(obj[i])
                else:
                    return None
            return tuple(rv)
        else:
            return None


class SimpleFormatter(LabelFormatter):
    def __init__(self, format_str='', **kwargs):
        super(SimpleFormatter, self).__init__(format_str=format_str, **kwargs)

    def _set_format_str(self, format_str):
        self._set_setting_field(format_str=format_str)

    def format(self, *args, **kwargs):
        if args:
            s = self.format_str % args
        elif kwargs:
            s = self.format_str.format(**kwargs)
        else:
            return self.set_timeout()
        if not self.col:
            return self.wrap(self.get_pre(), 0) +\
                self.wrap(s, 1)
        else:
            return self.wrap(f'[color={self.col}]{self.get_pre()}[/color]', 0) +\
                self.wrap(f'[color={self.col}]{s}[/color]', 1)


class SimpleFieldFormatter(SimpleFormatter):
    def __init__(self, fields=[], **kwargs):
        super(SimpleFieldFormatter, self).__init__(fields=fields, **kwargs)

    def _set_fields(self, fields):
        self._set_setting_field(fields=fields)

    def format(self, fitobj, *args, **kwargs):
        flds = self.get_fields(self.fields, fitobj)
        if flds is None:
            return self.set_timeout()
        else:
            return super(SimpleFieldFormatter, self).format(*flds, *args, **kwargs)


class TimeFieldFormatter(SimpleFieldFormatter):
    def __init__(self, example_conf={'time': 3723}, fields=['%ttime'], **kwargs):
        super(TimeFieldFormatter, self).__init__(
            name='Time', format_str='%d:%02d:%02d', example_conf=example_conf,
            timeout='-:--:--', fields=fields, **kwargs)


class DoubleFormatter(LabelFormatter):
    def __init__(self, f1='', f2='', post='',
                 colmax='#32cb00', colmin='#fdd835',
                 **kwargs):
        super(DoubleFormatter, self).__init__(
            f1=f1, f2=f2, post=post,
            colmin=colmin, colmax=colmax, **kwargs)

    def _set_f1(self, f1):
        self._set_setting_field(f1=f1)

    def _set_f2(self, f2):
        self._set_setting_field(f2=f2)

    def _set_post(self, post):
        self._set_setting_field(post=post)

    def _set_colmin(self, colmin):
        self._set_setting_field(colmin=colmin)

    def _set_colmax(self, colmax):
        self._set_setting_field(colmax=colmax)

    @classmethod
    def get_colors_to_set(cls):
        return dict(Background=_SETCOLOR_BACKGROUND,
                    Main=_SETCOLOR_MAIN,
                    OK=_SETCOLOR_OK,
                    Warning=_SETCOLOR_WARNING,
                    Error=_SETCOLOR_ERROR)

    def format(self, v1, v2, *args, **kwargs):
        if v1 is None or v2 is None:
            return self.set_timeout()
        else:
            col1 = self.col
            s1 = self.f1 % v1
            s2 = self.f2 % v2
            if v1 is None or v1 == v2:
                col2 = self.col
                pre = 'norm'
            elif v1 > v2:
                col2 = self.colmax
                pre = 'max'
            else:
                col2 = self.colmin
                pre = 'min'
            if not col1 or not col2 or not self.col:
                return self.wrap(self.get_pre(), 0) +\
                    self.wrap(f'{s1}', 1, pref=pre) +\
                    self.wrap(f'({s2})', 2) +\
                    self.wrap(self.post, 4)
            else:
                return self.wrap(f'[color={self.col}]{self.get_pre()}[/color]', 0) +\
                    self.wrap(f'[color={col2}]{s1}[/color] ', 1) +\
                    self.wrap(f'[color={self.col}]([/color][color={col1}]{s2}[/color][color={self.col}])[/color]', 2) +\
                    self.wrap(f'[color={self.col}]{self.post}[/color]', 4)


class DoubleFieldFormatter(DoubleFormatter):
    def __init__(self, fields=[], **kwargs):
        super(DoubleFieldFormatter, self).__init__(fields=fields, **kwargs)

    def _set_fields(self, fields):
        self._set_setting_field(fields=fields)

    def format(self, fitobj, *args, **kwargs):
        flds = self.get_fields(self.fields, fitobj)
        if flds is None:
            return self.set_timeout()
        else:
            return super(DoubleFieldFormatter, self).format(*flds, *args, **kwargs)


class SessionFormatter(LabelFormatter):
    def __init__(self, pre='$D Ses: ', **kwargs):
        super(SessionFormatter, self).__init__(
            name='Session', pre=pre, type='session', timeouttime=0,
            example_conf=dict(datestart=1584885218699), **kwargs)

    def format(self, v1, *args, **kwargs):
        if not isinstance(v1, (int, float)):
            v1 = self.get_fields(['datestart'], v1)
            if not v1:
                return self.set_timeout()
            else:
                v1 = v1[0]
        datepubo = datetime.fromtimestamp(v1 / 1000)
        datepub = datepubo.strftime('%H:%M:%S %Y-%m-%d')
        if not self.col:
            return self.wrap(self.get_pre(), 0) +\
                self.wrap(datepub, 1)
        else:
            return self.wrap(f'[color={self.col}]{self.get_pre()}[/color]', 0) +\
                self.wrap(f'[color={self.col}]{datepub}[/color]', 1)


class UserFormatter(LabelFormatter):
    def __init__(self, pre='$D User: ', **kwargs):
        super(UserFormatter, self).__init__(
            pre=pre, example_conf=dict(name='Matteo', height=178, weight=75, birthday=480358067),
            type='user', timeouttime=0, name='user', **kwargs)

    def format(self, v1, *args):
        flds = self.get_fields(["name", "height", "weight", "birthday"], v1)
        if flds:
            datepubo = datetime.fromtimestamp(flds[3])
            years = int((datetime.now()-datepubo).days / 365.25)
            if not self.col:
                return self.wrap(self.get_pre(), 0) +\
                    self.wrap(f"{flds[0]} {flds[1]}cm/{flds[2]}kg/{years}y", 1)
            else:
                return self.wrap(f'[color={self.col}]{self.get_pre()}[/color]', 0) +\
                    self.wrap(f"[color={self.col}]{flds[0]} {flds[1]}cm/{flds[2]}kg/{years}y[/color]", 1)
        else:
            return self.set_timeout()


class StateFormatter(LabelFormatter):
    def __init__(self, pre='$D ST: ', post='',
                 colmax='#32cb00', colmin='#fdd835', **kwargs):
        super(StateFormatter, self).__init__(
            name='State', pre=pre, type='state',
            example_conf=dict(state=DEVSTATE_DISCONNECTED), post=post, timeouttime=0,
            colmax=colmax, colmin=colmin, **kwargs)

    def _set_post(self, post):
        self._set_setting_field(post=post)

    def _set_colmin(self, colmin):
        self._set_setting_field(colmin=colmin)

    def _set_colmax(self, colmax):
        self._set_setting_field(colmax=colmax)

    def format(self, v1, *args, **kwargs):
        if not isinstance(v1, int):
            v1 = self.get_fields(['state'], v1)
            if not v1:
                return self.set_timeout()
            else:
                v1 = v1[0]
        pref = 'min'
        if v1 == DEVSTATE_INVALIDSTEP:
            col1 = self.colerror
            s1 = 'invalid'
            pref = 'error'
        elif v1 == DEVSTATE_DISCONNECTED:
            col1 = self.colerror
            s1 = 'disconnected'
            pref = 'error'
        elif v1 == DEVSTATE_UNINIT:
            col1 = self.col
            s1 = 'uninit'
            pref = 'norm'
        elif v1 == DEVSTATE_IDLE:
            col1 = self.colmin
            s1 = 'idle'
        elif v1 == DEVSTATE_ONLINE:
            col1 = self.colmax
            s1 = 'online'
            pref = 'max'
        elif v1 == DEVSTATE_CONNECTING:
            col1 = self.colmin
            s1 = 'connecting'
        elif v1 == DEVSTATE_DISCONNECTING:
            col1 = self.colmin
            s1 = 'disconnecting'
        elif v1 == DEVSTATE_SEARCHING:
            col1 = self.colmin
            s1 = 'searching'
        elif v1 == DEVSTATE_DPAUSE:
            col1 = self.colmin
            s1 = 'pause'
        elif v1 == DEVSTATE_CONNECTED:
            col1 = self.colmax
            s1 = 'connected'
            pref = 'max'
        if not col1 or not self.col:
            return self.wrap(self.get_pre(), 0) +\
                self.wrap(f'{s1}', 1, pref=pref) +\
                self.wrap(self.post, 4)
        else:
            return self.wrap(f'[color={self.col}]{self.get_pre()}[/color]', 0) +\
                self.wrap(f'[color={col1}]{s1}[/color]', 1, pref=pref) +\
                self.wrap(f'[color={self.col}]{self.post}[/color]', 4)

    @classmethod
    def get_colors_to_set(cls):
        return dict(Background=_SETCOLOR_BACKGROUND,
                    Main=_SETCOLOR_MAIN,
                    OK=_SETCOLOR_OK,
                    Warning=_SETCOLOR_WARNING,
                    Error=_SETCOLOR_ERROR)
