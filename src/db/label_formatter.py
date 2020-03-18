import abc

from db import SerializableDBObj
from util.const import (DEVSTATE_CONNECTED, DEVSTATE_CONNECTING,
                        DEVSTATE_DISCONNECTED, DEVSTATE_DISCONNECTING,
                        DEVSTATE_DPAUSE, DEVSTATE_IDLE, DEVSTATE_INVALIDSTEP,
                        DEVSTATE_ONLINE, DEVSTATE_SEARCHING, DEVSTATE_UNINIT)


class LabelFormatter(SerializableDBObj, abc.ABC):
    __table__ = 'label'
    __columns__ = (
        '_id',
        'view',
        'name',
        'device',
        'example',
        'pre',
        'classname',
        'settings',
        'background',
        'orderd',
    )
    __columns2field__ = {
        'orderd': 'order'
    }

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
            device integer not null,
            example text not null,
            pre text,
            classname text not null,
            settings text,
            timeout text,
            background text,
            orderd integer not null,
            FOREIGN KEY(view) REFERENCES view(_id) ON DELETE CASCADE,
            FOREIGN KEY(device) REFERENCES device(_id) ON DELETE CASCADE);
        '''

    def __init__(self, name='', example=(), pre='$D: ', timeout='[color=#ffeb3b]---[/color]', **kwargs):
        super(LabelFormatter, self).__init__(name=name, example=example, pre=pre, **kwargs)
        if self.classname is None:
            self.classname = self.fullname()
        if self.settings:
            for key in self.settings:
                setattr(self, key, self.settings[key])

    @abc.abstractmethod
    def format(self, *args, **kwargs):
        pass

    @staticmethod
    def wrap_color(txt, col='#ffeb3b'):
        return f'[color={col}]{txt}[/color]'

    def set_timeout(self):
        return self.get_pre() + self.timeout

    def reset(self):
        self.order = None
        self.background = None

    def print_example(self):
        return self.format(*self.example)

    def get_title(self):
        return self.deviceobj.get_alias() + " " + self.name

    def get_pre(self):
        return self.pre.replace('$D', self.deviceobj.get_alias())

    def set_device(self, deviceobj):
        self.deviceobj = deviceobj
        self.device = deviceobj.get_id()

    def set_background(self, background):
        self.background = background

    def set_order(self, order):
        self.order = order

    @staticmethod
    def get_fields(fldnamelst, obj):
        rv = []
        for i in fldnamelst:
            if i in obj:
                rv.append(obj[i])
            else:
                return None
        return tuple(rv)


class SimpleFormatter(LabelFormatter):

    def __init__(self, name='', example=(), format_str='', col='#212121', pre='$D: ', **kwargs):
        super(SimpleFormatter, self).__init__(name=name, example=example, pre=pre, format_str=format_str, col=col, **kwargs)
        if self.settings is None:
            self.settings = dict()
        if 'format_str' not in self.settings:
            self.settings.update(dict(format_str=self.format_str, col=self.col))

    def format(self, *args, **kwargs):
        if args:
            s = self.format_str % args
        elif kwargs:
            s = self.format_str.format(**kwargs)
        else:
            s = self.format_str
        return self.get_pre() + f'[color={self.col}]' + s + '[/color]'


class SimpleFieldFormatter(SimpleFormatter):
    def __init__(self, name='', example=(), format_str='', col='#212121', pre='$D: ', fields=[], **kwargs):
        super(SimpleFieldFormatter, self).__init__(
            name=name, example=example, format_str=format_str,
            col=col, pre=pre, fields=fields, **kwargs)
        if self.settings is None:
            self.settings = dict()
        if 'fields' not in self.settings:
            self.settings.update(dict(fields=self.fields))

    def format(self, fitobj, *args, **kwargs):
        flds = self.get_fields(self.fields, fitobj)
        if flds is None:
            return ''
        else:
            return super(SimpleFieldFormatter, self).format(*flds, *args, **kwargs)


class TimeFieldFormatter(SimpleFormatter):
    def __init__(self, col='#212121', pre='$D: ', fields=[], **kwargs):
        super(TimeFieldFormatter, self).__init__(
            name='Time', example=(3723,), format_str='%d:%02d:%02d',
            col=col, pre=pre, fields=fields, **kwargs)

    def format(self, fitobj, *args, **kwargs):
        tm = self.get_fields(self.fields, fitobj)[0]
        hrs = tm // 3600
        tm -= hrs * 3600
        mins = tm // 60
        tm -= mins * 60
        secs = tm % 60
        return super(TimeFieldFormatter, self).format(*(hrs, mins, secs), *args, **kwargs)


class DoubleFormatter(LabelFormatter):
    def __init__(self, name='', example=(), f1='', f2='', post='',
                 col='#212121', colmax='#32cb00', colmin='#ffeb3b',
                 colerror='#f44336', pre='$D: ', **kwargs):
        super(DoubleFormatter, self).__init__(
            name=name, example=example,
            col=col, pre=pre, f1=f1, f2=f2, post=post,
            colmin=colmin, colmax=colmax, colerror=colerror, **kwargs)
        if self.settings is None:
            self.settings = dict()
        if 'f1' not in self.settings:
            self.settings.update(dict(
                f1=self.f1,
                f2=self.f2,
                post=self.post,
                col=self.col,
                colmin=self.colmin,
                colmax=self.colmax,
                colerror=self.colerror
                ))

    def format(self, v1, v2, *args, **kwargs):
        if v1 is None:
            col1 = self.colerror
            s1 = '--'
        else:
            col1 = self.col
            s1 = self.f1 % v1
        if v2 is None:
            col2 = self.colerror
            s2 = '--'
        else:
            s2 = self.f2 % v2
            if v1 is None or v1 == v2:
                col2 = self.col
            elif v1 > v2:
                col2 = self.colmax
            else:
                col2 = self.colmin
        return self.get_pre() + f'[color={col2}]{s1}[/color] [color={self.col}]([/color][color={col1}]{s2}[/color][color={self.col}])[/color]' + self.post


class DoubleFieldFormatter(DoubleFormatter):
    def __init__(self, name='', example=(), f1='', f2='', post='',
                 col='#212121', colmax='#32cb00', colmin='#ffeb3b',
                 colerror='#f44336', pre='$D: ', fields=[], **kwargs):
        super(DoubleFieldFormatter, self).__init__(
            name=name, example=example, f1=f1, f2=f2, post=post,
            col=col, colmax=colmax, colmin=colmin, colerror=colerror, pre=pre,
            fields=fields, **kwargs)
        if self.settings is None:
            self.settings = dict()
        if 'fields' not in self.settings:
            self.settings.update(dict(
                fields=self.fields
                ))

    def format(self, fitobj, *args, **kwargs):
        flds = self.get_fields(self.fields, fitobj)
        if flds is None:
            return ''
        else:
            return super(DoubleFieldFormatter, self).format(*flds, *args, **kwargs)


class StateFormatter(LabelFormatter):
    def __init__(self, name='', col='#212121', pre='ST $D: ', post='',
                 colmax='#32cb00', colmin='#ffeb3b', colerror='#f44336', **kwargs):
        super(StateFormatter, self).__init__(
            name=name, example=(DEVSTATE_DISCONNECTED,), col=col, post=post,
            colmax=colmax, colmin=colmin, colerror=colerror, pre=pre, **kwargs)
        if self.settings is None:
            self.settings = dict()
        if 'colmin' not in self.settings:
            self.settings.update(dict(
                col=self.col,
                post=self.post,
                colmin=self.colmin,
                colmax=self.colmax,
                colerror=self.colerror
                ))

    def format(self, v1, *args, **kwargs):
        if not isinstance(v1, int):
            v1 = self.get_fields(['state'])[0]
        if v1 == DEVSTATE_INVALIDSTEP:
            col1 = self.colerror
            s1 = 'invalid'
        elif v1 == DEVSTATE_DISCONNECTED:
            col1 = self.colerror
            s1 = 'disconnected'
        elif v1 == DEVSTATE_UNINIT:
            col1 = self.col
            s1 = 'uninit'
        elif v1 == DEVSTATE_IDLE:
            col1 = self.colmin
            s1 = 'idle'
        elif v1 == DEVSTATE_ONLINE:
            col1 = self.colmax
            s1 = 'online'
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
        return self.get_pre() + f'[color={col1}]{s1}[/color]' + self.post
