from os.path import dirname, join

from db import SerializableDBObj


class Device(SerializableDBObj):
    __table__ = 'device'
    __columns__ = (
        '_id',
        'name',
        'alias',
        'type',
        'additionalsettings',
        'orderd'
    )
    __columns__ = (
        'name',
        'alias',
        'additionalsettings',
        'orderd'
    )

    __create_table_query__ =\
        '''
        create table if not exists device
                (_id integer primary key autoincrement,
                description text,
                address VARCHAR(17),
                name VARCHAR(30),
                alias VARCHAR(30) not null UNIQUE,
                type integer not null,
                additionalsettings TEXT DEFAULT ''
                enabled integer not null,
                orderd integer not null DEFAULT 999);
        '''

    def __lt__(self, other):
        return self.orderd < other.orderd

    def __le__(self, other):
        return self.orderd <= other.orderd

    def __gt__(self, other):
        return self.orderd > other.orderd

    def __ge__(self, other):
        return self.orderd >= other.orderd

    def __init__(self, dbitem=None, **kwargs):
        super(Device, self).__init__(dbitem, **kwargs)
        self.enabled = 1

    def get_name(self):
        return self.name

    def get_alias(self):
        return self.alias

    def set_alias(self, v):
        self.alias = v

    def get_additionalsettings(self):
        return self.additionalsettings

    def set_additionalsettings(self, v):
        self.additionalsettings = v

    def get_orderd(self):
        return self.orderd

    def set_orderd(self, v):
        self.orderd = v

    def get_type(self):
        return self.type

    def get_icon(self):
        return join(dirname(__file__), "..", "ico", self.type + '_ico.png')

    def get_address(self):
        return self.address
