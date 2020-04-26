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
    __wherejoin__ = None
    __joinclass__ = None
    __load_order__ = None

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
    async def load1m(cls, db, rowid=None, **kwargs):
        pls = await cls.loadbyid(db, rowid=rowid, **kwargs)
        if cls.__wherejoin__ and cls.__joinclass__:
            for p in pls:
                cond = {cls.__wherejoin__: p.rowid}
                pls2 = await SerializableDBObj.get_class(cls.__joinclass__).loadbyid(db, rowid=None, **cond)
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
        order = ''
        if cls.__load_order__:
            order = ' ORDER BY '
            for k, i in cls.__load_order__.items():
                order += f'{k} {i},'
            order = order[0:-1]
        for k, i in kwargs.items():
            if k == 'order':
                order = f' ORDER BY {i}'
            else:
                cond += f" {'WHERE' if not cond else 'AND'} P.{k}=? "
                subs += (i,)
        query += cond + order
        _LOGGER.debug(f'Querying {query} (pars={subs})')
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

    @staticmethod
    def _clone(el):
        rv = el
        if isinstance(el, dict):
            rv = el.copy()
            for k, v in el.items():
                rv[k] = SerializableDBObj._clone(v)
        elif isinstance(el, list):
            rv = list(el)
            k = 0
            for v in el:
                rv[k] = SerializableDBObj._clone(v)
                k += 1
        elif isinstance(el, tuple):
            rv = tuple()
            for v in el:
                rv += (SerializableDBObj._clone(v),)
        elif isinstance(el, SerializableDBObj):
            rv = el.clone()
        return rv

    def clone(self):
        dct = SerializableDBObj._clone(vars(self))
        cl = self.__class__()
        cl.process_kwargs(dct)
        return cl

    def _set_single_field(self, key, val):
        fln = self.fld(key)
        if (fln.find('settings') >= 0 or fln.find('conf') >= 0) and isinstance(val, str):
            v = json.loads(val)
        else:
            v = val
        try:
            setmethod = getattr(self, f'_set_{fln}')
            setmethod(v)
        except Exception:
            # _LOGGER.debug(f'SetMethod not found for {fln} ({traceback.format_exc()})')
            setattr(self, fln, v)

    def process_kwargs(self, dbitem):
        if dbitem:
            for key in dbitem.keys():
                self._set_single_field(key, dbitem[key])

    def __init__(self, dbitem=None, **kwargs):
        self.process_kwargs(dbitem)
        if dbitem:
            ks = dbitem.keys()
        else:
            ks = ()
        for i in kwargs.copy():
            if i in ks:
                del kwargs[i]
        self.process_kwargs(kwargs)
        for c in self.__columns__:
            f = self.fld(c)
            try:
                getattr(self, f)
            except AttributeError:
                setattr(self, f, None)
                # _LOGGER.debug(f'Set {self.__class__.__name__}.{f} ({c}) = None')
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
        return isinstance(s, str) and re.search(r'^\$([a-zA-Z0-9,\._]+)~(.+)$', s)

    def serialize(self):
        dct = dict(vars(self))
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
        self._set_single_field(name, val)

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
                            _LOGGER.debug(f'Items arr {k}')
                            items2 = []
                            for it in k:
                                items2.append(SerializableDBObj.deserialize(it))
                            dct[d] = items2
                        else:
                            dct[d] = SerializableDBObj.deserialize(k, k)
                    _LOGGER.debug(f'Deserialized {dct}')
                    cl = SerializableDBObj.get_class(rer.group(1))()
                    cl.process_kwargs(dct)
                    return cl
            # else:
            #     _LOGGER.debug(f'Invalid serialized str {jsons}')
        except Exception:
            _LOGGER.error(f'Deserialize error {traceback.format_exc()}')
        return rv

    async def delete(self, db, commit=True):
        rv = False
        if self.rowid:
            async with db.cursor() as cursor:
                values = (self.rowid,)
                query = f'DELETE FROM {self.__table__} WHERE {self.__id__}=?'
                _LOGGER.debug(f'Deleting: {query} (par={values})')
                await cursor.execute(query, values)
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
            v = self.f(t)
            if v is not None:
                if isinstance(v, dict):
                    v = json.dumps(v)
                values.append(v)
                colnames.append(t)
                strcol += '?,' if key is None else f'{t}=?,'
        strcol = strcol[0:-1]
        if key:
            async with db.cursor() as cursor:
                values.append(key)
                query = f'UPDATE {self.__table__} SET {strcol} WHERE {self.__id__}=?'
                _LOGGER.debug(f'Updating: {query} (par={values})')
                await cursor.execute(query, tuple(values))
                if cursor.rowcount <= 0:
                    return False
        else:
            async with db.cursor() as cursor:
                query = f'INSERT OR IGNORE into {self.__table__} ({",".join(colnames)}) VALUES ({strcol})'
                _LOGGER.debug(f'Inserting: {query} (par={values})')
                await cursor.execute(query, tuple(values))
                if cursor.rowcount <= 0:
                    return False
                self.rowid = cursor.lastrowid
                self.s(self.__id__, self.rowid)
        if self.__wherejoin__:
            items = self.f('items')
            if items is None:
                items = []
            cond = {self.__wherejoin__: self.rowid}
            _LOGGER.debug(f'Rowid = {self.rowid}')
            itemsold = await SerializableDBObj.get_class(self.__joinclass__).loadbyid(db, rowid=None, **cond)
            for it in itemsold:
                if it not in items:
                    rv = await it.delete(db, commit=False)
                    if not rv:
                        _LOGGER.warning(f'Failed to save {query}')
                        return False
            for it in items:
                it._set_single_field(self.__wherejoin__, self.rowid)
                rv = await it.to_db(db, commit=False)
                _LOGGER.debug(f'Saving item[{rv}] {it}')
                if not rv:
                    _LOGGER.warning(f'Failed to save {query}')
                    return False
        if commit:
            await db.commit()
        return True
