from db import SerializableDBObj


class View(SerializableDBObj):
    __table__ = 'view'
    __columns__ = (
        '_id',
        'name',
        'active'
    )

    __update_columns__ = (
        'name',
        'active'
    )

    __create_table_query__ =\
        '''
        create table if not exists view
            (_id integer primary key,
            name text not null,
            active integer default 0);
        '''

    def __init__(self, *args, **kwargs):
        super(View, self).__init__(*args, **kwargs)
        self.set_connected_devices()

    def set_connected_devices(self):
        items = self.f('items')
        self.connected_devices = []
        if items:
            for it in items:
                if it.device not in self.connected_devices:
                    self.connected_devices.append(it.device)

    def set_items(self, items):
        super(View, self).set_items(items)
        self.set_connected_devices()

    def get_connected_devices(self):
        return self.connected_devices
