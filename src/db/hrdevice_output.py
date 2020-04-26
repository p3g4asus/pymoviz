from db import SerializableDBObj


class HRDeviceOutput(SerializableDBObj):
    __table__ = 'hrdeviceSV'
    __columns2field__ = {
        'ctimems': 'timeRms',
        'ctimeabsms': 'timeRAbsms',
        'opul': 'pulse',
        'ojoule': 'joule',
        'oworn': 'worn',
        'cbeats': 'nBeatsR'
    }
    __columns__ = (
        '_id',
        'ctimems',
        'ctimeabsms',
        'opul',
        'ojoule',
        'oworn',
        'cbeats',
        'intervals_conf',
        'session'
    )

    __update_columns__ = (
        'ctimems',
        'ctimeabsms',
        'opul',
        'ojoule',
        'oworn',
        'cbeats'
    )

    __create_table_query__ =\
        '''
            create table if not exists hrdeviceSV
                (_id integer primary key,
                ctimems Integer not null,
                ctimeabsms Integer DEFAULT 0,
                opul Integer not null,
                oworn Integer not null,
                ojoule Integer not null,
                cbeats Integer not null,
                session Integer not null,
                intervals_conf text,
                FOREIGN KEY(session) REFERENCES session(_id) ON DELETE CASCADE);
        '''
