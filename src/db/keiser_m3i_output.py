from db import SerializableDBObj


class KeiserM3iOutput(SerializableDBObj):
    __table__ = 'keiserSV'
    __columns2field__ = {
        'otime': 'time',
        'ctime': 'timeR',
        'ctimems': 'timeRms',
        'ctimeabsms': 'timeRAbsms',
        'odist': 'distance',
        'cdist': 'distanceR',
        'ocal': 'calorie',
        'ospd': 'speed',
        'opul': 'pulse',
        'orpm': 'rpm',
        'owatt': 'watt',
        'oinc': 'incline'
    }
    __columns__ = (
        '_id',
        'otime',
        'ctime',
        'ctimems',
        'ctimeabsms',
        'odist',
        'cdist',
        'ocal',
        'ospd',
        'opul',
        'orpm',
        'owatt',
        'oinc',
        'session'
    )

    __update_columns__ = (
        'otime',
        'ctime',
        'ctimems',
        'ctimeabsms',
        'odist',
        'cdist',
        'ocal',
        'ospd',
        'opul',
        'orpm',
        'owatt',
        'oinc'
    )

    __create_table_query__ =\
        '''
        create table if not exists keiserSV
            (_id Integer primary key,
            otime Integer not null,
            ctime Integer not null,
            ctimems Integer not null,
            ctimeabsms Integer DEFAULT 0,
            odist real not null,
            cdist real not null,
            ocal Integer not null,
            ospd real not null,
            opul Integer not null,
            orpm Integer not null,
            owatt Integer not null,
            oinc Integer not null,
            session Integer not null,
            FOREIGN KEY(session) REFERENCES session(_id) ON DELETE CASCADE);
        '''
