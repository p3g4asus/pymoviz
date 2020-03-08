from db import SerializableDBObj


class Session(SerializableDBObj):
    __table__ = 'session'
    __columns__ = (
        '_id',
        'mainid',
        'device',
        'datestart',
        'settings',
        'user'
    )

    __update_columns__ = (
        'mainid',
        'datestart',
        'settings',
    )

    __create_table_query__ =\
        '''
        create table if not exists session
            (_id integer primary key,
            mainid integer,
            device integer not null,
            datestart Integer not null,
            exported Integer DEFAULT 65535,
            settings text,
            user Integer not null,
            FOREIGN KEY(user) REFERENCES user(_id) ON DELETE CASCADE,
            FOREIGN KEY(device) REFERENCES device(_id) ON DELETE CASCADE);
        '''
