"""
ISAM data types with MySQL supporting
$Id: ISAMSupporter.py, v 1.0 2008/05/21 12:00:00 Exp $

*** Checked 07/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

import sys, re
from types import ListType, TupleType, DictType, StringType, IntType, FloatType, LongType, ComplexType
from zLOG import LOG, DEBUG, INFO, ERROR

from DateTime import DateTime
from Missing import MV

from AccessControl.SecurityManagement import get_ident
from Globals import Persistent, default__class_init__ as InitializeClass
from ZPublisher import Publish

from Acquisition import Implicit, aq_get, aq_base, aq_parent, aq_inner
from ExtensionClass import Base

import Config

from logging import getLogger
logger = getLogger( 'ISAMSupporter' )

IsDebug = None

PythonDictTypes       = ( type({}), )
PythonListTypes       = ( type(()), type([]) )
PythonNumericTypes    = ( IntType, FloatType, LongType, ComplexType )
PythonStringTypes     = ( type(''), type(DateTime()), )
PythonDateTime        = ( type(DateTime()), )

default_engine        = 'MYISAM'
default_character_set = ''
datetime_format       = '%Y-%m-%d %H:%M:%S'

end_of_query          = '|\n'


class ISAMBase( Persistent, Implicit, Base ):
    """
    Abstract base class supported MyISAM data objects.
    The goal of the class is keeping data inside SQL data tables instead of ZODB container.
    """
    __implements__ = 'z2MyISAMInterface'

    def _IsDebug( self ):
        try: return self.aq_parent.getPortalObject().aq_parent.getProperty('DEBUG_ISAMSupporter')
        except: return None

    def __init__( self, id, descriptor, container=None ):
        """ Initialize class instance
        """
        self.id = id

        # Object's descriptor structure
        # -----------------------------
        #   <sql_table_name> -- object's table name
        #   <columns>        -- object's columns structure, list: [ (<id>, <sql_type>, <index>), ... ]
        #   <instance_type>  -- object's Python type
        #   <engine>         -- engine type for current table

        self.sql_table_name = descriptor[0] or id
        self.columns = descriptor[1]
        self.instance_type = descriptor[2]
        self.engine = descriptor[3] or default_engine
        self.container = container

        self.setup()

    def __len__( self ):
        # Returns container's size
        # ------------------------
        return self.getSize()
    #
    #   SQLDB properties =========================================================================================
    #
    def getId( self ):
        return getattr(self, 'id', None)

    def getSqlTableName( self ):
        return getattr(self, 'sql_table_name', None)

    def getColumns( self, ids=None ):
        if type(self.columns) is StringType:
            columns = getattr(Config, self.columns, None)
        else:
            columns = self.columns
        return ids and [ id for id, spec, index in columns ] or columns

    def getSize( self ):
        pass
    #
    #   SQLDB functions ==========================================================================================
    #
    def connection( self ):
        # Checks, opens and returns SQL connection instance
        # -------------------------------------------------
        x = getattr(Publish, 'getSqlConnection', None)
        try:
            object = self.aq_parent
        except:
            object = getattr(self, 'container', None) or self
        return x is not None and x(object=object) or None

    def run( self, query, max_rows=1000, mode=None, no_raise=None, **kw ):
        # Runs SQL query
        # --------------
        IsDebug = self._IsDebug()
        if not query:
            if IsDebug:
                logger.info("run checks no query: %s" % query)
            return None
        else:
            if IsDebug:
                LOG('ISAMSupporter.%s' % self.getId(), DEBUG, 'query: %s' % query)

        DB = self.connection()

        if DB is None:
            logger.error("connection is broken, TID: %s, query:\n%s" % ( get_ident(), query ))
            return None

        try:
            res = DB.query( query, max_rows )
        except:
            if no_raise: return None
            raise

        del DB

        if not mode or type(res) != type(()):
            return res

        # Description and result set:
        # keys of description: 'name', 'type', 'width', 'null'
        # ----------------------------------------------------
        desc, rs = res

        # 1) Simple item
        # --------------
        if mode == 1 or mode == 'item':
            try:
                return rs and rs[0][0] or None
            except:
                return None

        # 2) Tuple of ( <description>, <result set> ):
        #    'description' of columns as a dictionary: {'<name>':(<type>, <null>, <width>)}
        #    'result set': tuple of columns values
        # ----------------------------------------
        elif mode == 2 or mode in ( 'default', ):
            mapping = {}
            for x in desc:
                mapping[x['name']] = ( x['type'], x['null'], x['width'] )
            return ( mapping, rs, )

        # 3) Mapping tuple ( <row 0>, <row 1>, ... ):
        #    'row' as a dictionary of columns: {'<name>':'<value>', ...}
        # --------------------------------------------------------------
        elif mode in ( 3,31 ) or mode in ( 'mapping', 'records', ):
            records = []
            for row in rs:
                mapping = {}
                for n in range(len(row)):
                    mapping[desc[n]['name']] = row[n]
                records.append( mapping )
            if mode == 31 or mode == 'mapping':
                return ( desc, records, )
            return records

        # 4) Description only
        # -------------------
        elif mode == 4 or mode.startswith( 'desc' ):
            return desc

        # 5) Simple list
        # --------------
        elif mode == 5 or mode in ( 'list','tuple' ):
            return [ x[0] for x in rs ]

        # Otherwise, result set ('recordset')
        # -----------------------------------
        return rs
    #
    #   Published object actions =================================================================================
    #
    def setup( self ):
        # Setup new ISAM object
        # ---------------------
        table = self.getSqlTableName()
        if not table:
            return

        sp = \
            "SHOW TABLES LIKE '%s'" % table

        if self.run( sp, mode='item' ):
            return

        sp = ''
        for id, spec, index in self.getColumns():
            sp += '%s %s, ' % ( id, spec )
            if not index: continue
            sp += '%s, ' % index
        sp = sp.strip()[:-1]

        engine = getattr(self, 'engine', default_engine)

        sp = \
            "CREATE TABLE IF NOT EXISTS %s(%s) ENGINE=%s" % ( table, sp, engine )

        self.run( sp )

    def _state( self, sort=None, reverse=None, mode=None, lock=None, **keys ):
        # Returns object valid state
        # --------------------------
        table = self.getSqlTableName()
        if not table:
            return None

        if keys and type(keys) in PythonDictTypes:
            where = ' WHERE %s' % ' AND '.join( \
                    [ '%s=%s' % ( x, make_value( keys[x] ) ) for x in keys.keys() ]
                )
        else:
            where = ''

        if lock and self.engine == 'INNODB':
            l = ' FOR UPDATE'
        else:
            l = ''

        if sort:
            if type(sort) not in PythonListTypes:
                x = [sort]
            else:
                x = sort
            order_by = ' ORDER BY %s' % ', '.join(x)
            if reverse:
                order_by += ' DESC'
        else:
            order_by = ''

        sp = \
            "SELECT * FROM %s%s%s%s" % ( table, where, order_by, l )

        return self._get( validate( sp ), mode=mode )

    def _set( self, sp, no_raise=None ):
        try:
            self.run( validate( sp ), no_raise=no_raise )
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.error("%s[%s] in set %s, query:\n%s" % ( exc_type, exc_value, self.getId(), sp ))

    def _get( self, sp, mode=None ):
        return self.run( validate( sp ), mode=( mode or 'recordset' ) )

    def _del( self, sp ):
        self.run( validate( sp ) )

    def where( self, keyword=None, **keys ):
        w = ''
        for x in keys.keys():
            if w:
                w += ' AND '
            w += '%s=%s' % ( x, make_value( keys[x] ) )
        if w and keyword:
            w = ' %s %s' % ( keyword, w )
        return w

InitializeClass( ISAMBase )


class ISAMMapping( ISAMBase ):
    """
    Mapping class supported MyISAM data objects.
    The goal of the class is keeping mapping data such as a dictionary inside SQL data tables.
    """
    __allow_access_to_unprotected_subobjects__ = 1

    def __init__( self, id, columns, engine=None, container=None ):
        """ Initialize class instance
        """
        if type(columns) is ListType and 'ID' not in [ x[0] for x in columns ]:
            default_columns = [ ( \
                    'ID', 'VARCHAR(50) CHARACTER SET latin1 COLLATE latin1_general_cs NOT NULL', 'UNIQUE INDEX USING BTREE(ID)' \
                ) ]
            default_columns.extend( columns )
        else:
            default_columns = columns

        descriptor = ( \
            None, \
            default_columns,
            DictType,
            engine,
            )

        ISAMBase.__init__( self, id, descriptor, container )

    def __setitem__( self, key, value ):
        if hasattr( self, key ):
            setattr( self, key, value )
            return
        else:
            self.set( key, value )

    def __getitem__( self, key ):
        # Returns item value
        # ------------------
        if hasattr( self, key ):
            return getattr( self, key, None )
        else:
            rs = self.get( key )
            return rs and rs[0] or None

    def __delitem__( self, key ):
        # Deletes item
        # ------------
        if hasattr( self, key ):
            delattr( self, key, None )
            return
        table = self.getSqlTableName()
        if not table:
            return

        sp = \
            "DELETE FROM %s WHERE ID=%s" % ( table, make_value( key ) )

        return self._del( sp )

    def has_key( self, key ):
        try:
            self[key]
        except KeyError:
            return 0
        else:
            return 1

    def set( self, key, value, no_raise=None, ignore=None ):
        # Adds new item value
        # -------------------
        table = self.getSqlTableName()
        if not table:
            return

        cols = self.getColumns( ids=1 )
        vals = [ key ]

        if type(value) in PythonDictTypes:
            cols = ['ID']
            for id, spec, index in self.getColumns():
                if not value.has_key(id):
                    continue
                cols.append( id )
                vals.append( value[id] )
        elif type(value) in PythonListTypes:
            vals.extend( list(value) )
        else:
            vals.append( value )

        cols = ', '.join(cols)
        vals = ', '.join( [ make_value( v ) for v in vals ] )

        mods = ''
        if ignore: mods = ' IGNORE'

        sp = \
            "DELETE FROM %s WHERE ID=%s" % ( table, make_value( key ) ) + end_of_query + \
            "INSERT%s INTO %s(%s) VALUES(%s)" % ( mods, table, cols, vals )

        self._set( sp, no_raise=no_raise )

    def get( self, key, columns=None, mode=None, default=None, **kw ):
        # Returns object items collection matched the given query (**kw)
        # ------------------------------------------------------------------
        # Arguments:
        #   'key'     -- ID value
        #   'columns' -- select columns list, PythonListType
        #   'mode'    -- type of returned result
        #   'default' -- value if result is emply
        #   'kw'      -- query items
        # --------------------------
        table = self.getSqlTableName()
        if not key or not table:
            return None

        if columns and type(columns) not in PythonListTypes:
            cols = [columns]
        else:
            cols = columns

        cols = ', '.join( [ x for x in self.getColumns( ids=1 ) if not cols or x in cols ] )
        if not cols:
            return default

        sp = \
            "SELECT %s FROM %s WHERE %s%s" % ( cols, table, make_id( key ), self.where( 'AND', **kw ) )

        return self._get( sp, mode=mode ) or default

    def keys( self ):
        # Returns object keys list
        # ------------------------
        state = self._state( sort='ID' )
        if not state:
            return ()
        rs = [ x[0] for x in state ]
        return rs

    def items( self ):
        # Returns object items list
        # -------------------------
        state = self._state( sort='ID' )
        if not state:
            return ()
        rs = [ ( x[0], x[1:] ) for x in state ]
        return rs

    def values( self ):
        # Returns object values list
        # --------------------------
        state = self._state( sort='ID' )
        if not state:
            return ()
        rs = [ x[1:] for x in state ]
        return rs


class ISAMTuple( ISAMBase ):
    pass


class ISAMList( ISAMBase ):
    """
    List class supported MyISAM data objects.
    The goal of the class is keeping list data such as a dictionary inside SQL data tables.
    """
    __allow_access_to_unprotected_subobjects__ = 1

    def __init__( self, id, columns, engine=None, container=None ):
        """ Initialize class instance
        """
        descriptor = ( \
            None, \
            columns,
            ListType,
            engine,
            )

        ISAMBase.__init__( self, id, descriptor, container )

    def get( self, sort=None, reverse=None, mode=None, lock=None, **keys ):
        # Returns object values list
        # --------------------------
        return self._state( sort=sort, reverse=reverse, mode=mode, lock=lock, **keys )

    def add( self, **values ):
        # Adds new object value
        # ---------------------
        table = self.getSqlTableName()
        if not table:
            return

        s = ''
        v = ''
        for x in values.keys():
            if s: 
                s += ', '
                v += ', '
            s += x
            v += make_value( values[x] )

        sp = \
            "INSERT INTO %s(%s) VALUES(%s)" % ( table, s, v )

        self._set( sp )

    def update( self, keys, **values ):
        # Updates object value
        # --------------------
        table = self.getSqlTableName()
        if not table:
            return

        s = ''
        for x in values.keys():
            if s: 
                s += ', '
            s += '%s=%s' % ( x, make_value( values[x] ) )

        sp = \
            "UPDATE %s SET %s%s" % ( table, s, self.where( 'WHERE', **keys ) )

        self._set( sp )

    def remove( self, **keys ):
        # Removes object value
        # --------------------
        table = self.getSqlTableName()
        if not table:
            return

        sp = \
            "DELETE FROM %s%s" % ( table, self.where( 'WHERE', **keys ) )

        self._del( sp )

def make_id( key ):
    if type(key) in PythonStringTypes and '%' in key:
        eq = ' LIKE '
    else:
        eq = '='
    return 'ID%s%s' % ( eq, make_value( key ) )

def make_value( x ):
    t = type(x)
    c = "'"
    if t in PythonNumericTypes:
        return str(x)
    elif x is None:
        return 'NULL'
    elif t in PythonDateTime:
        v = x.strftime(datetime_format)
        v = re.sub(r'00\:00\:00', '', v)
    else:
        v = checkQuote( str(x) )
    return c + v.strip() + c

def checkQuote( s, size=None ):
    x = str(s)
    if size and len(x) > size:
        x = x[0:size]
    x = re.sub(r'\\', r"\\\\", x)
    x = re.sub(r'\'', r"\\'", x)
    x = re.sub(r'\"', r'\\"', x)
    x = re.sub(r'[\f\r\t\v\n]+', r'', x)
    return x

def validate( s ):
    x = re.sub(r'\'NULL\'(?i)', r'NULL', s)
    x = re.sub(r'\'None\'', r'NULL', x)
    x = re.sub(r'None', r'NULL', x)
    return x
