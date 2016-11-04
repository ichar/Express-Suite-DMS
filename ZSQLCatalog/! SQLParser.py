##############################################################################
#
# Copyright (c) 2008 Zope Corporation and Contributors. All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""
SQL query parser.
$Id: SQLParser.py 2008-04-15 12:00:00 $

*** Checked 22/09/2008 ***

"""
import re
from zLOG import LOG, DEBUG, ERROR, INFO

from time import strftime, localtime
from types import IntType, FloatType, LongType, ComplexType, BooleanType, StringTypes
from DateTime import DateTime
from Missing import MV

PythonDictTypes       = ( type({}), )
PythonListTypes       = ( type(()), type([]) )
PythonNumericTypes    = ( IntType, FloatType, LongType, ComplexType )
PythonStringTypes     = ( type(''), type(DateTime()), )

default_root_indexes  = ( 'uid', 'path', )

default_root_columns  = { \
    'RID'             : ( 'INT',        8, 'UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY', '', '' ),
    'uid'             : ( 'VARCHAR',  500, 'CHARACTER SET latin1 COLLATE latin1_general_cs NOT NULL', '', 'UNIQUE INDEX (%s)', ),
    'path'            : ( 'VARCHAR',  500, 'CHARACTER SET latin1 COLLATE latin1_general_cs NOT NULL', '', 'INDEX (%s)',        ),
    'rDate'           : ( 'TIMESTAMP',  0, '',                  '', '',                           ),
}

default_extensions_columns = { \
    'extID'           : ( 'VARCHAR',   50, 'ASCII NOT NULL',    '', '', ),
    'extPrefix'       : ( 'CHAR',       2, 'ASCII NULL',        '', '', ),
    'extType'         : ( 'INT',        1, '',                  '', '', ),
    'extSpec'         : ( 'VARCHAR',  100, '',                  '', '', ),
    'extTable'        : ( 'CHAR',      50, 'ASCII NOT NULL',    '', '', ),
    'extColumn'       : ( 'CHAR',      50, 'ASCII NOT NULL',    '', '', ),
    'extSize'         : ( 'INT',        4, '',                  '', '', ),
    'extComma'        : ( 'CHAR',       1, '',                  '', '', ),
    'extIsIndexable'  : ( 'TINYINT',    1, 'DEFAULT 0',         '', '', ),
}

default_indexes_columns = { \
    'idxID'           : ( 'CHAR',      50, 'ASCII NOT NULL',    '', '', ),
    'idxPrefix'       : ( 'CHAR',       2, 'ASCII NULL',        '', '', ),
    'idxExtType'      : ( 'CHAR',      20, 'ASCII NOT NULL',    '', '', ),
    'idxTable'        : ( 'CHAR',      50, 'ASCII NOT NULL',    '', '', ),
    'idxSpec'         : ( 'VARCHAR',  100, '',                  '', '', ),
    'idxEngine'       : ( 'CHAR',      10, 'ASCII NULL',        '', '', ),
}

simple_type_columns = { \
    'RID'             : ( 'INT',        8, 'UNSIGNED NOT NULL', 'FOREIGN KEY (RID) REFERENCES %(root)s (RID) ON DELETE CASCADE ON UPDATE NO ACTION', 'UNIQUE INDEX (%s)', ),
    'attrValue'       : ( '', 0, '', '', '', ),
    'rDate'           : ( 'TIMESTAMP',  0, '',                  '', '', ),
 }

list_type_columns = { \
    'RID'             : ( 'INT',        8, 'UNSIGNED NOT NULL', 'FOREIGN KEY (RID) REFERENCES %(root)s (RID) ON DELETE CASCADE ON UPDATE NO ACTION', 'INDEX (%s)', ),
    'attrValue'       : ( '', 0, '', '', '', ),
    'attrPos'         : ( 'INT',        2, 'UNSIGNED',          '', '', ),
    'attrIsList'      : ( 'TINYINT',    1, 'DEFAULT 1',         '', '', ),
    'attrIsKeyword'   : ( 'TINYINT',    1, 'DEFAULT 0',         '', '', ),
    'rDate'           : ( 'TIMESTAMP',  0, '',                  '', '', ),
}

keyword_type_columns = { \
    'RID'             : ( 'INT',        8, 'UNSIGNED NOT NULL', 'FOREIGN KEY (RID) REFERENCES %(root)s (RID) ON DELETE CASCADE ON UPDATE NO ACTION', 'INDEX (%s)', ),
    'attrName'        : ( 'CHAR',      30, 'ASCII NOT NULL',    '', '', ),
    'attrValue'       : ( 'VARCHAR',   50, '',                  '', '', ),
    'attrPos'         : ( 'INT',        2, 'UNSIGNED',          '', '', ),
    'attrIsList'      : ( 'TINYINT',    1, 'DEFAULT 0',         '', '', ),
    'attrIsKeyword'   : ( 'TINYINT',    1, 'DEFAULT 1',         '', '', ),
    'rDate'           : ( 'TIMESTAMP',  0, '',                  '', '', ),
}

# XXX
tree_type_columns = { \
    'RID'             : ( 'INT',        8, 'UNSIGNED NOT NULL', 'FOREIGN KEY (RID) REFERENCES %(root)s (RID) ON DELETE CASCADE ON UPDATE NO ACTION', '', ),
    'attrValue'       : ( '', 0, '', '', '', ),
    'attrLevel'       : ( 'INT',        2, 'UNSIGNED',          '', '', ),
    'rDate'           : ( 'TIMESTAMP',  0, '',                  '', '', ),
}

default_root          = 'root'
default_indexes       = 'indexes'
default_extensions    = 'extensions'

default_engine        = '' #'InnoDB' 
default_character_set = '' #'utf8'
datetime_format       = '%Y-%m-%d %H:%M:%S'
date_format           = '%Y-%m-%d'

TYPE          = 0
SIZE          = 1
SPECIFICATION = 2
CONSTRAINT    = 3
INDEX         = 4

StringTypes   = ( 'CHAR', 'VARCHAR',  )
DateTypes     = ( 'DATE', 'DATETIME', 'TIME', )
TextTypes     = ( 'TEXT', 'MEDIUMTEXT', 'LONGTEXT', )
BlobTypes     = ( 'BLOB', 'MEDIUMBLOB', 'LONGBLOB', 'TINYBLOB', )

FullTextTypes = BlobTypes + TextTypes

end_of_query  = '|\n'

"""
    Globals definitions and settings =============================================================================
"""
def getRootName( context ):
    return context.getSqlRootName() or default_root

def getTableName( context, name ):
    return context.getSqlTableName( name )

def getPrefix( context ):
    return context.getSqlPrefix() or ''

def default_root_column_ids( context ):
    columns = context.getSqlRootColumns() or default_root_columns
    return [ x for x in columns.keys() if x in default_root_indexes ]
"""
    Setup Catalog Database =======================================================================================
"""
def init_db( context ):
    # Returns query for creating of ZSQLCatalog database
    # --------------------------------------------------
    return \
        create_db( context.getSqlDBName() )

def init_root( context, name ):
    # Returns query for creating of roots' ZSQLCatalog table
    # ------------------------------------------------------
    prefix = getPrefix( context )
    columns = context.getSqlRootColumns() or default_root_columns
    
    query = \
        "SHOW TABLES LIKE '%s%s'" % ( prefix, '%' )
    items = context.run( query, no_action=1, mode='list' )

    ids = ', '.join(items)
    sp_drop_catalog_tables = ids and 'DROP TABLES %s%s' % ( ids, end_of_query ) or ''
    
    return \
        create_table( default_extensions, default_extensions_columns.copy() ) + end_of_query + \
        create_table( default_indexes, default_indexes_columns.copy() ) + end_of_query + \
        "DELETE FROM %s WHERE extPrefix='%s'" % ( default_extensions, prefix ) + end_of_query + \
        "DELETE FROM %s WHERE idxPrefix='%s'" % ( default_indexes, prefix ) + end_of_query + \
        sp_drop_catalog_tables + \
        create_table( name, columns, prefix=prefix )

def clear( context, table=None ):
    # Returns query for clearing all rows from ZSQLCatalog table
    # ----------------------------------------------------------
    prefix = getPrefix( context )
    root = getRootName( context )

    sp_remove_from_extension = "DELETE FROM %s"
    sp = sp_remove_from_extension % ( table or root )

    if not table:
        query = \
            "SELECT idxTable FROM %s i WHERE i.idxEngine='MYISAM' AND i.idxPrefix='%s'" % ( \
                default_indexes, prefix )
        items = context.run( query, no_action=1, mode='list' )

        for x in items:
            sp += end_of_query + sp_remove_from_extension % x

    return sp
"""
    Setup Catalog extensions =====================================================================================
"""
def add_extension( context, name, ext_type, ext_spec, as_root=None, default_value=None, engine=None, \
                   indexable=None ):
    # Adds new extension
    # ------------------
    # Arguments:
    #   'name'          -- extension 'id'
    #   'ext_type'      -- extension type (ZSQLCatalog.extensionTypes)
    #   'ext_spec'      -- SQL field type
    #   'as_root'       -- flag: add extension into 'root' table (SimpleType only)
    #   'default_value' -- reserved
    #   'indexable'     -- flag: add associated index
    # -----------------------------------------------
    prefix = getPrefix( context )
    root = getRootName( context )
    table = getTableName( context, name )

    if not as_root:
        query = \
            "SELECT 1 FROM %s WHERE extTable='%s' AND extPrefix='%s'" % ( \
                default_extensions, table, prefix )
        if context.run( query, no_action=1, mode='item' ):
            return None

    extension_type, extension_name, columns = getExtensionInfo( ext_type, with_columns=1 )
    t, s, o = parseSQLType( ext_spec )

    value = list(columns['attrValue'])
    value[TYPE] = type = t.upper()
    value[SIZE] = size = int(s)
    value[SPECIFICATION] = o
    value[CONSTRAINT] = ''

    if not indexable:
        pass
    elif indexable == 1:
        value[INDEX] = 'INDEX %s%s%s' % ( \
            prefix, name, getIndexSpec( as_root, extension_name, name=name, type=type, size=size ) )
    elif indexable == 2:
        value[INDEX] = 'FULLTEXT(attrValue)'

    # Make roots' new field
    if as_root:
        columns = { name : tuple(value) }
        table = root
        alter = 1

    # Make attrValue extension
    else:
        columns['attrValue'] = tuple(value)
        alter = 0

    # Try to run action before
    query = _table( name, columns, extension_name, alter=alter, prefix=prefix, root=root, engine=engine )
    context.run( query, no_action=1 )

    # Register new extension
    keys = getKeys( default_extensions_columns.copy() )
    values = ''

    for x in keys:
        if x == 'extID':
            values += "'%s'" % name
        elif x == 'extPrefix':
            values += "'%s'" % prefix
        elif x == 'extType':
            values += "%s" % extension_type
        elif x == 'extSpec':
            values += "'%s'" % ext_spec
        elif x == 'extTable':
            values += "'%s'" % table
        elif x == 'extColumn':
            values += "'%s'" % ( alter and name or 'attrValue' )
        elif x == 'extSize':
            values += "%s" % size
        elif x == 'extComma':
            values += type in StringTypes + DateTypes and '\x22\x27\x22' or \
                      type in FullTextTypes and '\x27\x22\x27' or "''"
        elif x == 'extIsIndexable':
            values += "%s" % indexable and '1' or '0'
        values += ', '

    values = values.strip()
    if values.endswith(','):
        values = values[0:len(values)-1]

    sp_insert_into_extensions = \
        delete_from_extension( name, prefix ) + end_of_query + \
        "INSERT INTO %s(%s) VALUES(%s)" % ( default_extensions, ', '.join(keys), values )

    return \
        sp_insert_into_extensions

def remove_extension( context, name ):
    # Removes extension
    # -----------------
    prefix = getPrefix( context )
    root = getRootName( context )

    rs = extension_data( context, name )
    if rs is None:
        return None
    extTable, extIsIndexable, extType, extComma, extSize = rs

    if extTable == root:
        # Try to run action before
        query = 'ALTER TABLE %s DROP %s' % ( extTable, name )
        context.run( query, no_action=1 )

        return delete_from_extension( name, prefix ) + end_of_query + \
               delete_from_indexes( name, prefix )
    return \
        drop_table( extTable, extension=1 )
"""
    Setup Catalog indexes ========================================================================================
"""
def add_index( context, name, ext_type, ext_spec, as_root=None, default_value=None, engine=None ):
    # Adds new index
    # --------------
    # Look at 'add_extension' arguments
    # ---------------------------------
    prefix = getPrefix( context )
    root = getRootName( context )
    table = getTableName( context, name )

    if table != root:
        query = \
            "SELECT 1 FROM %s WHERE idxTable='%s' AND idxPrefix='%s'" % ( \
                default_indexes, table, prefix )
        if context.run( query, no_action=1, mode='item' ):
            return None

    query = \
        "SELECT extTable, extIsIndexable, extType, extSize FROM %s WHERE extTable='%s'" % ( \
            default_extensions, table )
    rs = context.run( query, mode='recordset', no_action=1 )

    if not rs:
        return add_extension( context, name, ext_type, ext_spec, as_root, default_value, indexable=1, \
            engine=engine )
    extTable, extIsIndexable, extType, extSize = rs[0]
    if extIsIndexable:
        return

    alter = extTable == getRootName( context ) and 1 or 0
    extension_name = getExtensionInfo( ext_type )

    spec = \
        "INDEX %s%s ON %s %s" % ( \
            prefix, name, extTable, getIndexSpec( alter, extension_name, name, size=extSize ) )
    sp_create_index = 'CREATE ' + spec

    # Try to run action before
    context.run( sp_create_index, no_action=1 )

    idxs = [( name, prefix, extension_name, extTable, spec, engine )]
    sp_insert_into_indexes = insert_into_indexes( idxs )

    sp_update_extensions = \
        "UPDATE %s SET extIsIndexable=1 WHERE extPrefix='%s' AND extID='%s'" % ( \
            default_extensions, prefix, name )

    return \
        delete_from_indexes( name, prefix ) + end_of_query + \
        sp_insert_into_indexes + end_of_query + \
        sp_update_extensions

def remove_index( context, name ):
    # Removes index
    # -------------
    prefix = getPrefix( context )

    rs = index_data( context, name )
    if rs is None:
        return None
    idxTable, idxExtType = rs

    # Try to run action before
    sp_drop_index = \
        "DROP INDEX %s%s ON %s" % ( prefix, name, idxTable )
    context.run( sp_drop_index, no_action=1 )

    sp_delete_from_indexes = delete_from_indexes( idxTable )
    sp_update_extensions = \
        "UPDATE %s SET extIsIndexable=0 WHERE extPrefix='%s' AND extID='%s'" % ( \
            default_extensions, prefix, name )

    return \
        sp_delete_from_indexes + end_of_query + \
        sp_update_extensions
"""
    Get SQL extension patterns ===================================================================================
"""
def insert_pattern( context, table ):
    # Returns 'insert' pattern for given table
    # ----------------------------------------
    root = getRootName( context )
    s = '%s'

    if table == root:
        schema = context.getSchema()
        # key, extComma
        rs = [ ( x[0], x[1][3] ) for x in schema if x[1][1] == root ]
        i = []
        v = []
        for x in rs:
            i.append( x[0] )
            c = x[1] or ''
            v.append( c + '%s' + c )
        i = i and ', ' + ', '.join(i) or ''
        v = v and ', ' + ', '.join(v) or ''
        return \
            "INSERT INTO %s(uid, path%s) VALUES ('%s', '%s'%s)" % ( root, i, s, s, v )
    else:
        query = \
            "SELECT extType, extComma FROM %s WHERE extTable='%s'" % ( default_extensions, table )
        try:
            t, c = context.run( query, no_action=1, mode='recordset' )[0]
        except:
            return None
        return \
            default_insert_pattern( table, t, c )

def default_insert_pattern( table, t, c ):
    s = '%s'
    i = 'RID, '
    v = s + ', '
    if t == 0:
        i += 'attrValue'
        v += c + s + c
    elif t == 1:
        i += 'attrValue, attrPos'
        v += c + s + c + ', ' + s
    elif t == 2:
        i += 'attrName, attrValue, attrPos, attrIsList'
        v += "'" + s + "', " + c + s + c + ', ' + s + ', ' + s
    return \
        "INSERT INTO %s(%s) VALUES (%s)" % ( table, i, v )

def update_pattern( context, table, name ):
    # Returns 'update' pattern for given table
    # ----------------------------------------
    root = getRootName( context )
    s = '%s'

    if table == root:
        schema = context.getSchema()
        # extComma
        rs = [ x[1][3] for x in schema if x[0] == name ]
        c = rs and rs[0] or "'"
        v = c + s + c
        return \
            "UPDATE %s SET %s=%s" % ( table, name, v ) + " WHERE RID=" + s
    else:
        query = \
            "SELECT extType, extComma FROM %s WHERE extTable='%s'" % ( \
                default_extensions, table )
        try:
            t, c = context.run( query, no_action=1, mode='recordset' )[0]
        except:
            return None
        return \
            "DELETE FROM %s" % table + " WHERE RID=" + s + end_of_query + \
            default_insert_pattern( table, t, c )
"""
    Get Catalog's properties and object metadata =================================================================
"""
def metadata( context, rid, query_items=None, root_values=None, for_indexes=None ):
    # Returns 'metadata' values
    # -------------------------
    # Arguments:
    #   'rid'           -- cataloged object 'rid'
    #   'query_items'   -- requested extensions list
    #   'root_values'   -- roots' values, selected before
    #   'for_indexes'   -- extensions' schema (by default - metadata)
    # ---------------------------------------------------------------
    root = getRootName( context )
    schema = context.getSchema( for_indexes=for_indexes )

    # Select from 'root' before
    if root_values is None:
        query = select_metadata( context, schema, table=root, rid=rid )
        rs = context.run( query, no_action=1, mode='records' )[0]
        if not rs: return {}
    else:
        rs = root_values.copy() or {}

    if query_items is None:
        extension_items = extensionItems( context )
    else:
        # extTable, key, extType
        extension_items = [ ( x[1][1], x[0], x[1][2] ) for x in schema if x[0] in query_items ]

    keys = [ x[0] for x in schema ]

    # Select from other extensions
    for x in extension_items:
        table, key, ext_type = x[0:3]
        if key not in keys:
            continue
        query = select_metadata( context, schema, table=table, rid=rid )
        values = context.run( query, no_action=1, mode='recordset' )
        rs[key] = parse_metadata( values, ext_type )

    if root_values is None and not for_indexes:
        return make_metadata_tuple( schema, rs )
    return rs

def index( context, key, query=None, sort_by_path=None, distinct=None, limit=None, offset=None ):
    # Returns 'index' values
    # ----------------------
    # Arguments:
    #   'key'           -- index name
    #   'query'         -- requested query
    #   'sort_by_path'  -- sort by path, Boolean
    #   'distinct'      -- distinct only, Boolean
    #   'limit'         -- limit max rows, Number
    #   'offset'        -- offset, skip it before, Number
    # ---------------------------------------------------
    root = getRootName( context )
    rid_name = '%s.RID' % root
    schema = context.getSchema( key=key, for_indexes=1 )
    i, table, ext_type, comma = schema[0:4]

    if table != root:
        if ext_type == 2:
            s = "attrName AS name, attrValue AS value, attrPos AS pos"
        elif ext_type == 1:
            s = "NULL AS name, attrValue AS value, attrPos AS pos"
        else:
            s = "NULL AS name, attrValue AS value, NULL AS pos"
        f = ', %s' % table
        w = '%s=%s.RID' % ( rid_name, table )
    else:
        s = 'NULL AS name, %s AS value, NULL AS pos' % key
        f = None
        w = None

    f, where = parse_query( context, root, query, f, w )

    if distinct:
        query = 'SELECT count(*) FROM (SELECT DISTINCT %s FROM %s%s%s) t1' % ( s, root, f, where )
    else:
        query = 'SELECT count(*) FROM %s%s%s' % ( root, f, where )

    total_rows = context.run( query, no_action=1, mode='item', max_rows=1 )

    if sort_by_path:
        order = ' ORDER BY uid'
    elif distinct:
        order = ' ORDER BY name, value, pos'
    else:
        order = ' ORDER BY %s' % rid_name
    if limit:
        order += ' LIMIT %d' % checkLimit( limit )
        if offset:
            order += ' OFFSET %d' % offset
        max_rows = 1000
    else:
        max_rows = checkLimit( limit )

    if distinct:
        query = 'SELECT DISTINCT %s FROM %s%s%s%s' % ( s, root, f, where, order )
    else:
        query = 'SELECT %s, uid, %s FROM %s%s%s%s' % ( rid_name, s, root, f, where, order )

    selected_items = context.run( query, no_action=1, mode='records', max_rows=max_rows )

    rs = []
    for x in selected_items:
        if distinct:
            n = x['name'] or ''
            v = x['value'] or 'NULL'
            p = x['pos'] or 0
            item = { 'name' : n, 'value' : v, 'pos' : p }
        else:
            n = x['name'] and x['name'] + '-' or ''
            v = x['value'] or 'NULL'
            p = x['pos'] and '-' + str(x['pos']) or ''
            item = { 'RID' : x['RID'], 'uid' : x['uid'], 'value' : "%s%s%s" % ( n, v, p ) }
        rs.append( item )

    return ( total_rows, rs, )

def rid( context, uid=None, path=None ):
    # Checks whether RID (unique record identifier) exists
    # ----------------------------------------------------
    if not ( uid or path ):
        raise AttributeError, "No 'uid or path' passed"
    if uid:
        return \
            "SELECT RID FROM %s WHERE uid='%s' LIMIT 1" % ( getRootName( context ), uid )
    if path:
        return \
            "SELECT RID FROM %s WHERE path='%s' LIMIT 1" % ( getRootName( context ), path )

def uids( context, path=None, rid=None, op=None ):
    # Returns uids of the cataloged object(s)
    # ---------------------------------------
    if not ( path or rid ):
        raise AttributeError, "Neither 'path' nor 'rid' passed"
    where = ''
    vop = validOperator( op )
    if path:
        where += "path='%s'" % path
    if rid:
        if where: where += vop and ' %s ' % vop or ' AND '
        where += "RID=%s" % rid
    return \
        "SELECT uid FROM %s WHERE %s" % ( getRootName( context ), where )

def paths( context, uid=None, rid=None, op=None ):
    # Returns paths of the cataloged object(s)
    # ----------------------------------------
    root = getRootName( context )
    where = ''
    if uid:
        where += "uid='%s'" % uid
    if rid:
        if where:
            vop = validOperator( op )
            where += vop and ' %s ' % vop or ' AND '
        where += "RID=%s" % rid
    if where:
        where = ' WHERE %s' % where
    return \
        "SELECT DISTINCT path FROM %s%s" % ( root, where )

def size( context, query=None ):
    # Catalog's size
    # --------------
    root = getRootName( context )
    rid_name = '%s.RID' % root

    if query:
        f, where = parse_query( context, root, query )
        query = \
            "SELECT count(*) FROM ( SELECT DISTINCT %s FROM %s%s%s ) t1" % ( rid_name, root, f, where )
    else:
        query = \
            "SELECT count(*) FROM %s" % root
    total_rows = context.run( query, no_action=1, mode='item', max_rows=1 )

    return total_rows
"""
    Get Catalog's extensions information =======================================================================
"""
def extensionItems( context ):
    # Returns extensions list
    # -----------------------
    prefix = getPrefix( context )
    root = getRootName( context )
    query = \
        "SELECT extTable, extID, extType FROM %s WHERE extPrefix='%s' AND extTable != '%s'" % ( \
            default_extensions, prefix, root )
    return context.run( query, no_action=1, mode='recordset' )

def extension_data( context, name ):
    # Returns extension' data for given name
    # --------------------------------------
    prefix = getPrefix( context )
    query = \
        "SELECT extTable, extIsIndexable, extType, extComma, extSize FROM %s " \
        "WHERE extPrefix='%s' AND extID='%s'" % ( \
            default_extensions, prefix, name )
    rs = context.run( query, mode='recordset', no_action=1 )
    if not rs:
        return None
    return rs[0]
"""
    Get Catalog's indexes information ============================================================================
"""
def indexTables( context, key=None ):
    # Returns indexed tables list as ( idxTable, isExtension )
    # --------------------------------------------------------
    # Arguments:
    #   'key' -- index (table) name
    # -----------------------------
    prefix = getPrefix( context )
    where = ''
    sp = "SELECT DISTINCT idxID, idxTable, idxExtType, idxSpec, " \
         "CASE WHEN i.idxID=e.extID THEN 1 ELSE 0 END AS isExtension " \
         "FROM %s i LEFT JOIN %s AS e ON e.extID=i.idxID " \
         "WHERE i.idxPrefix='%s'" % ( default_indexes, default_extensions, prefix )
    if key:
        sp += " AND i.idxID='%s'" % key
    return sp

def indexItems( context, table, key=None ):
    # Returns Database native indexes list
    # ------------------------------------
    index_name = getTableName( context, key )
    where = ''
    if not key:
        pass
    elif table == index_name:
        where = " and Column_name='attrValue'"
        table = index_name
    else:
        where = " and Column_name='%s'" % key
    return \
        "SHOW INDEX FROM %s WHERE Column_name != 'RID'%s" % ( table, where )

def indexSize( context, table, key, distinct='distinct' ):
    # Returns index' size
    # -------------------
    if table == getTableName( context, key ):
        key = 'attrValue'
    return \
        "SELECT count(*) FROM (select %s %s from %s) t" % ( distinct or '', key, table or default_root )

def indexType( context, table, key=None ):
    # Returns index' type (BTREE, FULLTEXT, ...)
    # ------------------------------------------
    query = indexItems( context, table, key )
    rs = context.run( query, mode='records', no_action=1 )
    return rs and [ x.get('Index_type') for x in rs ] or []

def index_data( context, name ):
    # Returns index' data for given name
    # ----------------------------------
    prefix = getPrefix( context )
    query = \
        "SELECT idxTable, idxExtType FROM %s WHERE idxPrefix='%s' AND idxID='%s'" % ( \
            default_indexes, prefix, name )
    rs = context.run( query, mode='recordset', no_action=1 )
    if not rs:
        return None
    return rs[0]
"""
    Catalog objects ==============================================================================================
"""
def append( context, metadata, uid, path ):
    # Insert new metadata (catalog new object)
    # ---------------------------------------
    prefix = getPrefix( context )
    root = getRootName( context )
    schema = context.getSchema()

    # Insert into 'root' before
    root_schema = [ x for x in schema if x[1][1] == root ]
    query = insert_metadata( context, root_schema, metadata, table=root, uid=uid, path=path )
    context.run( query, no_action=1 )

    # Get new RID
    query = rid( context, uid )
    new_rid = context.run( query, no_action=1, mode='item' )
    if new_rid is None:
        LOG('SQLParser.append', ERROR, 'new_rid is None\nuid:%s\nquery:%s\nmetadata:%s' % ( \
            uid, query, metadata ))
        return ''

    #query = \
    #    "SELECT extTable FROM %s WHERE extPrefix='%s' AND extTable != '%s'" % (
    #        default_extensions, prefix, root )
    #extension_items = context.run( query, no_action=1, mode='list' )

    # Insert all extensions
    extensions_schema = [ x for x in schema if x[1][1] != root ]
    sp = update_metadata( context, extensions_schema, metadata, rid=new_rid, no_delete=1 )

    if context._IsDebug():
        LOG('SQLParser', DEBUG, 'append [%s] query:\n%s\nmetadata:%s\nrid:%s' % ( \
            uid, sp, metadata, new_rid ))
    return sp

def update( context, metadata, rid, uid ):
    # Update metadata (cataloging of existing object)
    # -----------------------------------------------
    if rid is None:
        LOG('SQLParser.update', ERROR, 'rid is None\nuid:%s\nmetadata:%s' % ( \
            uid, metadata ))
        return ''

    schema = context.getSchema()
    sp = update_metadata( context, schema, metadata, rid=rid )

    if context._IsDebug():
        LOG('SQLParser', DEBUG, 'update [%s] query:\n%s\nmetadata:%s\nrid:%s' % ( \
            uid, sp, metadata, rid ))
    return sp

def remove( context, rid ):
    # Delete metadata (uncataloging of object)
    # ----------------------------------------
    if rid is None:
        LOG('SQLParser.remove', ERROR, 'rid is None')
        return ''

    prefix = getPrefix( context )
    root = getRootName( context )
    if rid is None:
        return ''

    sp_remove_from_extension = "DELETE FROM %s WHERE RID=%s"
    sp = sp_remove_from_extension % ( root, rid )

    query = \
        "SELECT idxTable FROM %s i WHERE i.idxEngine='MYISAM' AND i.idxPrefix='%s'" % ( \
           default_indexes, prefix )
    #query = \
    #    "SELECT extTable FROM %s i, %s e " \
    #    "WHERE i.idxID=e.extID AND i.idxPrefix=e.extPrefix AND i.idxEngine='MYISAM' AND i.idxPrefix='%s'" % ( \
    #        default_indexes, default_extensions, prefix )
    items = context.run( query, no_action=1, mode='list' )

    for x in items:
        sp += end_of_query + sp_remove_from_extension % ( x, rid )

    if context._IsDebug():
        LOG('SQLParser', DEBUG, 'remove query:\n%s\nrid:%s' % ( \
            sp, rid ))
    return sp

def apply_index( context, rid, key, value ):
    # Index object (not metadata, explicit indexes)
    # ---------------------------------------------
    if rid is None:
        LOG('SQLParser.apply_index', ERROR, 'rid is None\nkey:%s\nvalue:%s' % ( \
            key, value ))
        return ''

    schema = [ ( key, context.getSchema( key=key, for_indexes=1 ), ) ]

    #query = "SELECT idxTable FROM %s i, %s e WHERE i.idxID=e.extID AND i.idxID='%s'" % ( \
    #    default_indexes, default_extensions, key )
    #index_items = context.run( query, no_action=1, mode='list' )

    metadata = ( value, )

    # Insert index value
    sp = update_metadata( context, schema, metadata, rid=rid, no_delete=None )

    if context._IsDebug():
        LOG('SQLParser', DEBUG, 'apply_index [%s] query:\n%s\nmetadata:%s\nrid:%s' % ( \
            key, sp, metadata, rid ))
    return sp

def apply_unindex( context, rid, key=None ):
    # Unindex object (not metadata only, explicit indexes)
    # ----------------------------------------------------
    if rid is None:
        LOG('SQLParser.apply_unindex', ERROR, 'rid is None\nkey:%s' % key)
        return ''

    if not key:
        return ''
    table = getTableName( context, key )

    if key:
        query = \
            "SELECT idxTable FROM %s i, %s e WHERE i.idxID=e.extID AND i.idxID='%s' AND i.idxTable='%s'" % ( \
                default_indexes, default_extensions, key, table )
        index_items = context.run( query, no_action=1, mode='list' )
        if not index_items:
            return None

    sp = \
        "DELETE FROM %s WHERE RID=%s" % ( table, rid )

    if context._IsDebug():
        LOG('SQLParser', DEBUG, 'apply_unindex [%s] query:\n%s\nrid:%s' % ( \
            key, sp, rid ))
    return sp
"""
    Searching ====================================================================================================
"""
def search( context, query, items=None, sort_index=None, reverse=None, limit=None, offset=None ):
    # Returns metadata selected by given query
    # ----------------------------------------
    schema = context.getSchema()
    root = getRootName( context )
    rid_name = '%s.RID' % root

    f, where = parse_query( context, root, query )

    sp = \
        "SELECT count(*) FROM ( SELECT DISTINCT %s FROM %s%s%s ) t1" % ( \
            rid_name, root, f, where )
    total_rows = context.run( sp, no_action=1, mode='item', max_rows=1 )

    if not total_rows:
        return ( total_rows, [], )

    order = ''
    if sort_index:
        s, f, where, order = parse_order_by( context, root, sort_index, reverse, f, where )
    else:
        s = ''
    max_rows = checkLimit( limit )
    if limit:
        order += ' LIMIT %d' % max_rows
        if offset:
            order += ' OFFSET %d' % offset

    root_items = [ x[0] for x in schema if x[1][1] == root and x[0] not in default_root_column_ids( context ) ]
    #simple_type_items = [ x[0] for x in schema if x[1][2] == 0 ]

    if root_items:
        s = ', '+', '.join(root_items) + s

    if items is None:
        query_items = [ x[1] for x in extensionItems( context ) ]
    else:
        query_items = items
    query_items = filter(None, map( lambda x, root_items=root_items: x not in root_items and x or None, \
                                    query_items ))
    sp = \
        "SELECT DISTINCT %s, uid, path%s FROM %s%s%s%s" % ( \
            rid_name, s, root, f, where, order )
    selected_items = context.run( sp, no_action=1, mode='recordset', max_rows=max_rows )

    rs = []
    for x in selected_items:
        # Check default root's key
        rid, uid, path = x[0:3]
        values = {}
        if root_items:
            # Collect root's metadata only
            for n in range(len(x[3:])):
                if n < len(root_items):
                    values[root_items[n]] = x[3+n]
        if query_items:
            # Get data from selected extensions
            values = metadata( context, rid, query_items=query_items, root_values=values )

        # Make output resultset
        rs.append( [ rid, make_metadata_tuple( schema, values ), uid, path, 0 ] )

    return ( total_rows, rs, )

def trees( context, query ):
    # Returns trees selected by given query
    # -------------------------------------
    root = getRootName( context )
    rid_name = '%s.RID' % root

    f, where = parse_query( context, root, query )
    s, f, where, order = parse_order_by( context, root, 'path', None, f, where )
    f += ', %s AS p' % getTableName( context, 'parent_path' )
    where += ' AND %s=p.RID' % rid_name

    sp = \
        "SELECT DISTINCT %s, path, p.attrValue FROM %s%s%s%s LIMIT 4000" % ( \
            rid_name, root, f, where, order )
    rs = context.run( sp, no_action=1, mode='recordset', max_rows=0 )

    return rs

def search_attributes( context, table, attr, created, query ):
    # Returns attribute values list
    # -----------------------------
    root = getRootName( context )
    created_name = '%s.created' % root

    attr_table = getTableName( context, table )
    attr_name = "a.attrName='%s'" % attr
    attr_value = 'a.attrValue'

    attr_created = "%s>='%s' AND %s<='%s'" % ( \
        created_name, created[0].strftime(date_format), created_name, created[1].strftime(date_format)
        )

    f, where = parse_query( context, root, query )
    f += ', %s AS a' % attr_table

    relation = ' AND a.RID=%s.RID' % root

    sp = \
        "SELECT DISTINCT %s FROM %s%s%s%s AND %s AND %s AND %s != '' ORDER BY %s LIMIT 1000" % ( \
            attr_value, root, f, where, relation, attr_name, attr_created, \
            attr_value, attr_value )
    rs = context.run( sp, no_action=1, mode='list', max_rows=0 )

    return rs

def parse_query( context, root, query, _from=None, _where=None ):
    # Major searching query attributes parser
    # ---------------------------------------
    # Search Query items (tuple):
    #   <key>, <value>, <table>, <ext_type>, <comma>
    # ----------------------------------------------
    if not query or type(query) != type([]):
        return ( _from or '', valid_where( _where ) )

    rid_name = '%s.RID' % root

    f = _from or ''  # 'from' and
    w = _where or '' # 'where' query clauses

    def value_mask( value, range ):
        r = ''
        if type(value) in PythonListTypes:
            r = ' in (%s)'
        else:
            if 'eq' in range:
                if type(value) == type('') and value.find('%') > -1:
                    r = ' LIKE %s'
                else:
                    r = '=%s'
                range = ''
            elif 'min' in range:
                r = '>=%s'
                range = range.replace('min', '')
            elif 'max' in range:
                r = '<=%s'
                range = range.replace('max', '')
        return ( r, range, )

    for x in query:
        try: 
            k, v, a, ext_type, c, none, size, engine, hasFullTextIndex = x[0:9]
        except:
            k, v, a, ext_type, c = x[0:5]
            hasFullTextIndex = 0 #'FULLTEXT' in indexType( context, a, k ) and 1 or 0
        if v in ( MV, None ):
            continue
        if a is None: a = root
        if a != root:
            k = 'attrValue'
        key = a + '.' + k
        t = type(v)
        sq = ''

        if t in PythonDictTypes:
            # attr query is a dictionary like this:
            # { 'query':<value tuple>[, 'range':<'min'|'max'|'min:max'][, 'operator':<'AND'|'OR'|'NOT'>] }
            q = v.get('query') or ()
            if type(q) not in PythonListTypes:
                q = [q]
            range = ( v.get('range') or 'eq' ).lower()
            op = validOperator( v.get('operator') )
            n = 0
            l = len(q)
            subq = 'select distinct RID from %s where ' % a
            sop = ''
            for x in q:
                n += 1
                # KeywordType index
                if type(x) in PythonDictTypes:
                    sw = ''
                    for an, av in x.items():
                        sw += '(%s.attrName=\'%s\' %s ' % ( a, an, op )
                        if type(av) == PythonDictTypes:
                            values = av['query']
                            ar = ( av.get('range') or 'eq' ).lower()
                        else:
                            if type(av) in PythonListTypes:
                                values = av
                            else:
                                values = [av]
                            ar = 'eq'
                        
                        for value in values:
                            mask, ar = value_mask(value, ar)
                            sw += key + mask % checkValueType(value, c)
                            if len(values) > 1:
                                sw += ' and '
                        sw += ')'
                        if len(x.keys()) > 1:
                            sw += ' or '
                # ListType or SimpleType index
                else:
                    mask, range = value_mask(x, range)
                    sw = key + mask % checkValueType(x, c)
                if n > 1:
                    sop = ' %s ' % op
                sq += sop + '%s IN (%s%s)' % ( rid_name, subq, sw )
            if sq:
                if n > 1:
                    sq = '(%s)' % sq
                if op == 'NOT':
                    sq = 'NOT %s' % sq
            a = root

        elif t in PythonListTypes:
            # attr query is a list(tuple)
            x = [ checkValueType(x, c) for x in v ]
            sq = key + ' IN (%s)' % ','.join(x)

        elif t in PythonStringTypes:
            # attr query is a simple string type
            if hasFullTextIndex:
                sq = 'MATCH(%s) AGAINST(%s)' % ( key, checkValueType(v, c).replace('%', '') )
            elif v.find('%') > -1:
                sq = key + ' LIKE ' + checkValueType(v, c)
            else:
                sq = key + '=' + checkValueType(v, c)

        elif t in PythonNumericTypes:
            # attr query is a number
            sq = key + '=' + checkValueType(v, c)

        else: continue

        if not sq: continue

        if a != root:
            f += ', %s' % a
            w = add_where_item( w, '%s=%s.RID' % ( rid_name, a ) )
        w = add_where_item( w, sq )

    return ( f, valid_where( w ) )

def parse_order_by( context, root, key, reverse=None, _from=None, _where=None ):
    # Order By parser
    # ---------------
    if not key:
        return ( '', _from or '', valid_where( _where ), '' )

    prefix = getPrefix( context )
    rid_name = '%s.RID' % root

    s = ''           # selected order item,
    f = _from or ''  # 'from' and
    w = _where or '' # 'where' query clauses

    if key not in default_root_indexes:
        query = \
            "SELECT idxTable, extColumn FROM %s i, %s e WHERE " \
               "i.idxID=e.extID AND i.idxPrefix=e.extPrefix AND i.idxID='%s' AND i.idxPrefix='%s'" % ( \
            default_indexes, default_extensions, key, prefix )
        rs = context.run( query, no_action=1, mode='recordset' )
        if not rs:
            return ( '', '', '' )
        a, c = rs[0]
        sortkey = 'sortkey'
        s = ', %s.%s AS %s' % ( a, c, sortkey )
    else:
        a = root
        sortkey = key

    if a != root:
        f += ', %s' % a
        w = add_where_item( w, '%s=%s.RID' % ( rid_name, a ) )
    o = ' ORDER BY %s' % sortkey
    if reverse:
        o += ' DESC'

    return ( s,f, valid_where( w ), o )
"""
    SQL Data Manipulation Queries Generator ======================================================================
"""
def create_db( database ):
    return \
        "CREATE DATABASE IF NOT EXISTS %s" % database

def create_table( name, columns, extension=None, prefix=None, root=None, engine=None ):
    return _table( name, columns, extension, prefix=prefix, root=root, engine=engine )

def alter_table( name, columns, extension=None, prefix=None, root=None, engine=None ):
    return _table( name, columns, extension, alter=1, prefix=prefix, root=root, engine=engine )

def drop_table( name, extension=None ):
    sp = "DROP TABLE IF EXISTS %s" % name
    if extension:
        sp += end_of_query + delete_from_extension( name )
    sp += end_of_query + delete_from_indexes( name )
    return sp

def _table( name, columns, extension, alter=None, prefix=None, root=None, engine=None ):
    # Makes a new table creating query
    table_engine = engine or default_engine
    table = '%s%s' % ( prefix or '', name )
    keys = getKeys(columns)
    if not keys:
        LOG('SQLParser', ERROR, 'new table [%s] no columns: %s' % ( table, columns ))
        return ''
    l = len(keys)

    idxs = []
    if alter:
        table = root
        sp = 'ALTER TABLE %s' % table
        c_pref = ' ADD COLUMN '
        i_pref = ' ADD '
    else:
        sp = 'CREATE TABLE IF NOT EXISTS %s(' % table
        c_pref = ''
        i_pref = ' '

    for n in range(l):
        key = keys[n]
        x = columns[key]
        sp += '%s%s %s' % ( c_pref, key, x[TYPE] )
        if x[SIZE]:
            sp += '(%s)' % x[SIZE]
        if x[SPECIFICATION]:
            sp += " %s" % x[SPECIFICATION]
        if checkConstraint( x[CONSTRAINT], table_engine ):
            c = x[CONSTRAINT]
            if '%' in c:
                c = c % { 'root' : root or '' }
            sp += ", %s" % c
        elif x[INDEX]:
            index = re.sub(r'\%s', key, x[INDEX])
            sp += ",%s%s" % ( i_pref, index )
            if key != 'RID':
                if alter: iid = key
                else: iid = extension and name or key
                # indexes columns: idxID, idxPrefix, idxExtType, idxTable, idxSpec, idxEngine
                idxs.append( ( iid, prefix or '', extension or 'SimpleType', table, index, table_engine ) )
        if n < l-1: sp += ', '

    if not alter:
        sp += ')'
        if default_character_set:
            sp += ' CHARACTER SET %s' % default_character_set
        if table_engine:
            sp += ' ENGINE %s' % table_engine

    if idxs:
        sp += end_of_query + insert_into_indexes( idxs )

    return sp

def _record( data, into_table=None, rid=None ):
    pass

def insert_metadata( context, schema, metadata, table, rid=None, uid=None, path=None ):
    # Returns metadata insert query
    # -----------------------------
    if table == getRootName( context ):
        data = [ ( 'root', [ uid, path ] + [ metadata[x[1][0]] for x in schema if x[1][1] == table ] ) ]
        ext_type = 0
        IsRoot = 1
    else:
        return ''
        #item = [ ( x[0], x[1][2], metadata[x[1][0]] ) for x in schema if x[1][1] == table ]
        #data = []
        #for k, t, v in item:
        #    values = v
        #    if type(v) not in PythonListTypes:
        #        values = [values]
        #    data.extend( [ ( k, x ) for x in values ] )
        #ext_type = item and item[0][1] or 0
        #IsRoot = 0

    pattern = context.getInsertPattern( table )

    #if context._IsDebug():
    #    LOG('SQLParser', DEBUG, 'insert_metadata table: %s, ext_type: %s, pattern:\n%s' % ( \
    #        table, ext_type, pattern ))
    #    IsDebug = 1
    #else:
    #    IsDebug = 0

    sp = ''
    for item in data:
        key, values = item
        if type(values) not in PythonListTypes:
            values = [values]

        try:
            IsValue, attrs = make_attrs( rid and [ rid, ] or [], values, ext_type, None, IsRoot=IsRoot )
            if not IsValue: continue
        except:
            LOG('SQLParser', ERROR, 'insert_metadata item:\n%s' % str(item))
            raise

        for n in range(len(attrs)):
            attr = attrs[n]
            try:
                si = validate( pattern % tuple(attr) )
            except:
                LOG('SQLParser', ERROR, 'insert_metadata attrs:%s' % attr)
                raise

            #if IsDebug:
            #    LOG('SQLParser', DEBUG, 'insert_metadata sp:\n%s' % si)
            sp += si + end_of_query

    return sp

def update_metadata( context, schema, metadata, rid, no_delete=None ):
    # Returns metadata update query
    # -----------------------------
    # key, extTable, extType, extSize, metadata
    data = [ ( x[0], x[1][1], x[1][2], x[1][5], metadata[x[1][0]] ) for x in schema ]

    #if context._IsDebug():
    #    LOG('SQLParser', DEBUG, 'data: %s' % data)
    #    IsDebug = 1
    #else:
    #    IsDebug = 0

    sp = ''
    for item in data:
        key, table, ext_type, ext_size, values = item
        x = context.getUpdatePattern( key )
        patterns = x.split( end_of_query )

        if len(patterns) == 2:
            delete_pattern = not no_delete and patterns[0] or None
            insert_pattern = patterns[1]
            update_pattern = None
        else:
            delete_pattern = insert_pattern = None
            update_pattern = patterns[0]

        if type(values) in PythonDictTypes:
            values = values.items()
        elif type(values) not in PythonListTypes:
            values = [values]

        #if IsDebug:
        #    LOG('SQLParser', DEBUG, 'update_metadata table: %s, ext_type: %s, pattern:\n%s, values:\n%s' % ( \
        #        table, ext_type, patterns, values ))

        su = ''
        p = 0
        for x in values:
            try:
                IsValue, attrs = make_attrs( [], [x], ext_type, ext_size, p=p )
                if not IsValue: continue
            except:
                LOG('SQLParser', ERROR, 'update_metadata item:\n%s' % x)
                raise

            for n in range(len(attrs)):
                attr = attrs[n]
                try:
                    if su: su += end_of_query
                    if delete_pattern is not None:
                        su += delete_pattern % str(rid) + end_of_query
                        delete_pattern = None
                    if insert_pattern is not None:
                        attr.insert( 0, str(rid) )
                        su += insert_pattern % tuple(attr)
                    else:
                        attr.append( str(rid) )
                        su += update_pattern % tuple(attr)
                    p += 1
                except:
                    LOG('SQLParser', ERROR, 'update_metadata attrs:%s' % attrs)
                    raise

        if su:
            su = validate( su )
            #if IsDebug:
            #    LOG('SQLParser', DEBUG, 'update_metadata sp:\n%s' % su)
            if sp: 
                sp += end_of_query
            sp += su

    return sp

def select_metadata( context, schema, table, rid ):
    # Returns metadata select query
    # -----------------------------
    root = getRootName( context )
    rid_name = '%s.RID' % root

    if table != root:
        s_from = '%s, %s' % ( root, table )
        s_where = '%s=%s.RID AND %s=%s' % ( rid_name, table, rid_name, str(rid) )
    else:
        s_from = root
        s_where = '%s=%s' % ( rid_name, str(rid) )

    s_items = ''

    for x in schema:
        if x[1][1] != table: continue
        ext_type = x[1][2]
        if table == root:
            s_items += s_items and ', ' or ''
            s_items += x[0]
        elif ext_type == 0:
            s_items = 'attrValue'
            break
        elif ext_type == 1:
            s_items = 'attrValue, attrPos'
            break
        elif ext_type == 2:
            s_items = 'attrName, attrValue, attrPos, attrIsList'
            break

    sp = 'SELECT %s FROM %s WHERE %s' % ( s_items, s_from, s_where )
    return sp

def insert_into_indexes( idxs ):
    # Adds new record into 'indexes' table
    # ------------------------------------
    sp = ''
    l = len(idxs)
    if l:
        for n in range(l):
            sp += "INSERT INTO %s(idxID, idxPrefix, idxExtType, idxTable, idxSpec, idxEngine)" % default_indexes
            sp += " VALUES('%s', '%s', '%s', '%s', '%s', '%s')" % idxs[n][0:6]
            if n < l-1: sp += end_of_query
    return validate( sp )

def delete_from_extension( name, prefix=None ):
    # Deletes given name from 'extensions'
    # ------------------------------------
    if prefix:
        return \
            "DELETE FROM %s WHERE extPrefix='%s' AND extID='%s'" % ( default_extensions, prefix, name )
    else:
        return \
            "DELETE FROM %s WHERE extTable='%s'" % ( default_extensions, name )

def delete_from_indexes( name, prefix=None ):
    # Deletes given name from 'indexes'
    # --------------------------------
    if prefix:
        return \
            "DELETE FROM %s WHERE idxPrefix='%s' AND idxID='%s'" % ( default_indexes, prefix, name )
    else:
        return \
            "DELETE FROM %s WHERE idxTable='%s'" % ( default_indexes, name )
"""
    Other helper functions =======================================================================================
"""
def getKeys( m, sorted=1 ):
    keys = m.keys()
    if sorted:
        keys.sort()
    return keys

def getExtensionInfo( ext_type, with_columns=None ):
    if not ( ext_type and ext_type in ( 1,2 ) ):
        extension_columns = simple_type_columns.copy()
        extension_name = 'SimpleType'
        extension_type = 0
    elif ext_type == 1:
        extension_columns = list_type_columns.copy()
        extension_name = 'ListType'
        extension_type = 1
    elif ext_type == 2:
        extension_columns = keyword_type_columns.copy()
        extension_name = 'KeywordType'
        extension_type = 2
    if with_columns:
        return ( extension_type, extension_name, extension_columns, )
    return extension_name

def getIndexSpec( alter, extension, name=None, type=None, size=None ):
    size = ( size and size >= 500 or type in FullTextTypes and not size ) and '(500)' or ''
    attr_value = 'attrValue'
    if extension == 'KeywordType':
        x = '(attrName, %s%s)' % ( attr_value, size )
    elif alter:
        size = size and size > 100 and '(100)' or ''
        x = '(%s%s)' % ( name, size )
    else:
        x = '(%s%s)' % ( attr_value, size )
    return x

def parseSQLType( ext_spec ):
    # ext_spec - just together: TYPE + SIZE + SPECIFICATION + CONSTRAINT
    r_spec = re.compile( r'([A-Za-z]+)(?:\(([\d]+)\))?(?:\s+([\w\s]+))?', re.I+re.DOTALL )
    t = s = o = None
    m = r_spec.search( ext_spec )
    if m:
        t = ext_spec[ m.start(1) : m.end(1) ]
        s = ext_spec[ m.start(2) : m.end(2) ] or 0
        o = ext_spec[ m.start(3) : m.end(3) ] or ''
    else:
        raise SyntaxError, 'Invalid field type for %s' % name
    return ( t, s, o )

def validOperator( op=None ):
    if not op:
        return 'AND'
    if op.upper() not in ( 'AND','OR','NOT','AND NOT','OR NOT' ):
        op = None
    return op

def parse_metadata( values, ext_type=None ):
    if ext_type == 2:
        items = {}
    elif ext_type == 1:
        items = []
    else:
        items = None
    for x in values:
        if not ext_type or ext_type == 0:
            v = x[0] or None
            items = v
            break
        elif ext_type == 1:
            v = x[0] or None
            p = x[1]
            items.insert( p, v )
        elif ext_type == 2:
            k = x[0]
            v = x[1] or MV
            p = x[2]
            l = x[3]
            if l:
                if not items.has_key(k):
                    items[k] = []
                items[k].insert( p, v )
            else:
                items[k] = v
    return items

def make_attrs( default, values, ext_type, ext_size=None, IsRoot=None, p=None ):
    IsValue = 0
    attrs = []
    #
    # Check attr extension type before
    #
    if ext_type == 2:
        if len(values) != 1 or values[0] in ( MV, None, ):
            return ( IsValue, attrs, )
        attr_name, attr_values = values[0]
        attr_name = checkQuote( attr_name )
        if type(attr_values) not in PythonListTypes:
            attr_values = [attr_values]
            attr_list = 0
            attr_pos = 0
        else:
            attr_list = 1
            attr_pos = 0
    elif ext_type == 1:
        attr_name = attr_list = None
        attr_values = [values]
        attr_pos = p or 0
    else:
        attr_name = attr_pos = attr_list = None
        attr_values = [values]
    #
    # Make attr tuples for every row
    #
    for attr_value in attr_values:
        row = default or []
        if type(attr_value) not in PythonListTypes:
            attr_value = [attr_value]
        for x in attr_value:
            t = type(x)
            if not x or x is MV:
                if t in PythonNumericTypes and x == 0:
                    v = 0
                elif not IsRoot:
                    continue
                else:
                    v = 'NULL'
            elif t is type(DateTime()):
                v = x.strftime(datetime_format)
            elif t in PythonListTypes:
                v = ','.join(x)
            else:
                v = x
            if attr_name is not None: row.append( attr_name )
            row.append( checkQuote( v, ext_size ) )
            if attr_pos is not None:
                row.append( attr_pos )
                attr_pos += 1
            if attr_list is not None: row.append( attr_list )
            IsValue = 1
        if row:
            attrs.append( row )
    return ( IsValue, attrs, )

def checkLimit( limit ):
    default = 1000
    try: max_rows = limit and int(limit)
    except: max_rows = 0
    return max_rows or default

def checkQuote( s, size=None ):
    x = str(s)
    if size and len(x) > size:
        x = x[0:size]
    x = re.sub(r'\\', r"\\\\", x)
    x = re.sub(r'\'', r"\\'", x)
    x = re.sub(r'\"', r'\\"', x)
    x = re.sub(r'\|', r'-', x)
    #x = re.sub(r'[\f\r\t\v\n]+', r'', x)
    return x

def validate( s ):
    x = re.sub(r'\'NULL\'(?i)', r'NULL', s)
    x = re.sub(r'\'None\'', r'NULL', x)
    x = re.sub(r'None', r'NULL', x)
    return x

def checkValueType( x, c ):
    t = type(x)
    if not x and t not in PythonNumericTypes:
        return c + c
    if t in PythonListTypes:
        return ', '.join([ c + str(i) + c for i in x ])
    if t is type(DateTime()):
        v = x.strftime(datetime_format)
        v = re.sub(r'00\:00\:00', '', v)
    else:
        v = checkQuote(x)
    return c + v.strip() + c

def add_where_item( w, i ):
    if not i: return w
    if w: s = w + ' %s ' % validOperator()
    else: s = ''
    s += i
    return s

def valid_where( w ):
    if w and 'WHERE' not in w: s = ' WHERE %s' % w
    else: s = w or ''
    return s

def make_metadata_tuple( schema, items, explicit=None ):
    res = []
    for key, x in schema:
        n, t, ext_type, c, none_is_enabled = x[0:5]
        if not items.has_key(key):
            if explicit: continue
            v = None
        else:
            v = items[key]
        if v is None and not none_is_enabled:
            v = ''
        res.append( v )
    #LOG('SQLParser', DEBUG, 'metadata tuple:\n%s' % str(res))
    return tuple(res)

def checkConstraint( constraint, engine ):
    if not constraint:
        return None
    if not engine:
        return 1
    if 'FOREIGN KEY' in constraint:
        if engine not in ( 'INNODB', ):
            return None
    return 1
