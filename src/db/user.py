from db import SerializableDBObj


class User(SerializableDBObj):
    __table__ = 'user'

    __create_table_query__ =\
        '''
        create table if not exists user
            (_id integer primary key,
            name text not null,
            weight Integer not null,
            height Integer not null,
            birthday Integer not null,
            male Integer not null);
        '''
    __columns__ = (
        '_id',
        'name',
        'weight',
        'height',
        'birthday',
        'male'
    )
