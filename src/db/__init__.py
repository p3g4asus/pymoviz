import importlib
import json
import re
import traceback

from util import init_logger

_LOGGER = init_logger(__name__)


class SerializableDBObj(object):

    # cls.__columns__

    # __create_table_query__

    __id__ = "_id"
    __columns__ = None
    __columns2field__ = dict()
    __table__ = None
    __create_table_query__ = None
    __update_columns__ = None

    @classmethod
    def fullname(o):
        # o.__module__ + "." + o.__class__.__qualname__ is an example in
        # this context of H.L. Mencken's "neat, plausible, and wrong."
        # Python makes no guarantees as to whether the __module__ special
        # attribute is defined, so we take a more circumspect approach.
        # Alas, the module name is explicitly excluded from __qualname__
        # in Python 3.

        module = o.__module__
        if module is None or module == str.__class__.__module__:
            return "," + o.__name__
        else:
            return module + "," + o.__name__

    @classmethod
    def get_class(cls, sclassname):
        if sclassname:
            try:
                classname = sclassname.split(',')
                foo = importlib.import_module(classname[0])
                return getattr(foo, classname[1])
            except Exception:
                _LOGGER.debug(f'get_class({sclassname}) Exception {traceback.format_exc()}')
        return cls

    @classmethod
    def select_string(cls, tablename='P', hasprefix=''):
        strcol = ''
        for t in cls.__columns__:
            strcol += f'{tablename}.{t} AS {hasprefix}{t},'
        return strcol[0:-1]

    @classmethod
    async def load1m(cls, db, clsm, wherejoin=None, rowid=None, **kwargs):
        pls = await cls.loadbyid(db, rowid=rowid, **kwargs)
        if wherejoin:
            for p in pls:
                cond = {wherejoin: p.rowid}
                pls2 = await clsm.loadbyid(db, rowid=None, **cond)
                p.set_items(pls2)
        return pls

    @classmethod
    async def loadbyid(cls, db, rowid=None, **kwargs):
        pls = []
        strcol = cls.select_string()
        query = f'''
            SELECT {strcol}
            FROM {cls.__table__} AS P
        '''

        if rowid is not None:
            kwargs[cls.__id__] = rowid
        cond = ''
        subs = ()
        for k, i in kwargs.items():
            cond += f" {'WHERE' if not cond else 'AND'} P.{k}=? "
            subs += (i,)
        query += cond
        _LOGGER.debug(f'Querying {query}')
        cursor = await db.execute(query, subs)
        async for row in cursor:
            keys = row.keys()
            clname = row['classname'] if 'classname' in keys else None
            pl = cls.get_class(clname)(dbitem=row)
            _LOGGER.debug("%s %s" % (cls.__name__, str(pl)))
            pls.append(pl)
        return pls

    @classmethod
    def fld(cls, key):
        return key if key not in cls.__columns2field__ else cls.__columns2field__[key]

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.rowid is not None and self.rowid == other.rowid

    def __str__(self):
        return str(vars(self))

    def set_items(self, items):
        self.items = items

    def clone(self):
        dct = vars(self)
        if 'items' in dct and dct['items']:
            for i in range(len(dct['items'])):
                dct['items'][i] = dct['items'][i].clone()
        return self.__class__(**dct)

    def __init__(self, dbitem=None, **kwargs):
        if dbitem:
            for key in dbitem.keys():
                setattr(self,
                        self.fld(key),
                        dbitem[key])
        for key in kwargs:
            if (key.find('settings') >= 0 or key.find('conf') >= 0) and isinstance(kwargs[key], str):
                v = json.loads(kwargs[key])
            else:
                v = kwargs[key]
            setattr(self, self.fld(key), v)
        for c in self.__columns__:
            f = self.fld(c)
            try:
                getattr(self, f)
            except AttributeError:
                setattr(self, f, None)
                _LOGGER.debug(f'Set {self.__class__.__name__}.{f} ({c}) = None')
        setattr(self, 'rowid', getattr(self, self.__id__))
        self.set_update_columns()

    def get_id(self):
        return self.rowid

    @classmethod
    def set_update_columns(cls):
        if cls.__update_columns__ is None:
            cls.__update_columns__ = cls.__columns__

    @staticmethod
    def is_serialized_str(s):
        return isinstance(s, str) and re.search(r'^\$([a-zA-Z0-9,\.]+)~(.+)$', s)

    def serialize(self):
        dct = vars(self)
        for d, k in dct.copy().items():
            if isinstance(k, SerializableDBObj):
                dct[d] = k.serialize()
            elif d.startswith('items'):
                items2 = []
                for it in k:
                    items2.append(it.serialize())
                dct[d] = items2
        return f'${self.fullname()}~' + json.dumps(dct)

    def s(self, name, val):
        setattr(self, self.fld(name), val)

    def _f(self, name, typetuple=None):
        try:
            a = getattr(self, self.fld(name))
        except AttributeError:
            a = None
        return None if typetuple and (a is None or not isinstance(a, typetuple)) else a

    def f(self, name, typetuple=None):
        if isinstance(name, (list, tuple)):
            lst = []
            for n in name:
                lst.append(self._f(n, typetuple))
            return lst
        else:
            return self._f(name, typetuple)

    def __contains__(self, key):
        return self._f(key) is not None

    def __getitem__(self, key):
        return getattr(self, self.fld(key))

    @staticmethod
    def deserialize(jsons, rv=None):
        try:
            rer = SerializableDBObj.is_serialized_str(jsons)
            if rer:
                dct = json.loads(rer.group(2))
                if dct:
                    for d, k in dct.copy().items():
                        if d.startswith('items'):
                            items2 = []
                            for it in k:
                                items2.append(SerializableDBObj.deserialize(it))
                            dct[d] = items2
                        else:
                            dct[d] = SerializableDBObj.deserialize(k, k)
                    return SerializableDBObj.get_class(rer.group(1))(**dct)
        except Exception:
            _LOGGER.error(traceback.format_exc())
        return rv

    async def delete(self, db, commit=True):
        rv = False
        if self.rowid:
            async with db.cursor() as cursor:
                await cursor.execute(
                    f'''
                    DELETE FROM {self.__table__} WHERE {self.__id__}=?
                    ''', (self.rowid,))
                rv = cursor.rowcount > 0
        if rv and commit:
            await db.commit()
        return rv

    async def to_db(self, db, commit=True):
        values = []
        colnames = []
        strcol = ''
        key = self.f(self.__id__)
        cols = self.__columns__ if key is None else self.__update_columns__
        for t in cols:
            v = self.f(self.fld(t))
            if v is not None:
                if isinstance(v, dict):
                    v = json.dumps(v)
                values.append(v)
                colnames.append(t)
                strcol += '?,' if key is None else f'{t}=?,'
        strcol = strcol[0:-1]
        if key:
            async with db.cursor() as cursor:
                await cursor.execute(
                    f'''
                    UPDATE {self.__table__} SET {strcol} WHERE {self.__id__}=?
                    ''',
                    (*tuple(values), key)
                )
                if cursor.rowcount <= 0:
                    return False
        else:
            async with db.cursor() as cursor:
                await cursor.execute(
                    f'''
                    INSERT OR IGNORE into {self.__table__} ({",".join(colnames)}) VALUES ({strcol})
                    ''',
                    tuple(values)
                )
                if cursor.rowcount <= 0:
                    return False
                self.rowid = cursor.lastrowid
                self.s(self.__id__, self.rowid)
        items = self.f('items')
        if items:
            for it in items:
                await it.to_db(db, commit=False)
        if commit:
            await db.commit()
        return True
