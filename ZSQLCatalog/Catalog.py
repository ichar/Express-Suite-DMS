##############################################################################
#
# Copyright (c) 2001 Zope Corporation and Contributors. All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.0 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE
#
##############################################################################
"""
ZSQLCatalog product.
$Id: ZSQLCatalog.py 2008-04-15 12:00:00 $

*** Checked 14/06/2009 ***

"""
import types
from zLOG import LOG, DEBUG, INFO
from DateTime import DateTime

import ExtensionClass

from Acquisition import Implicit, aq_parent
from Missing import MV
from Lazy import LazyMap, LazyCat, LazyValues
from CatalogBrains import AbstractCatalogBrain, NoBrainer
from Globals import Persistent

import SQLParser

import logging
logger = logging.getLogger('ZSQLCatalog.Catalog')

IsCheckBase = 1
IsDebug = None

SequenceTypes = ( types.ListType, types.TupleType, )

try:
    from DocumentTemplate.cDocumentTemplate import safe_callable
except ImportError:
    # Fallback to python implementation to avoid dependancy on DocumentTemplate
    def safe_callable( ob ):
        # Works with ExtensionClasses and Acquisition.
        if hasattr(ob, '__class__'):
            return hasattr(ob, '__call__') or isinstance(ob, types.ClassType)
        else:
            return callable(ob)

### SQL Queryer ###

def run( context, action, max_rows=1000, mode='recordset', no_raise=None, no_action=None, clear=None, **kw ):
    if None in ( context, action, ):
        return None
    return aq_parent(context).run( action, max_rows, mode, \
        no_raise, no_action, clear, \
        **kw
        )

def view( context, action, **kw ):
    method = getattr( SQLParser, action, None )
    if method is None:
        return None
    return apply( method, ( aq_parent(context), ), kw )


class CatalogError( Exception ):
    pass

class Catalog( Persistent, Implicit, ExtensionClass.Base ):
    """
    An Object Catalog.

    An Object Catalog maintains a table of object metadata, and a series of manageable indexes
    to quickly search for objects (references in the metadata) that satisfy a search query.
    """
    _v_brains = NoBrainer
    _v_log = None

    def _IsDebug( self ):
        return self.aq_parent._IsDebug()

    def __init__( self, vocabulary=None, brains=None ):
        #
        # Initialize catalog attributes
        #
        self._initschema()

        if brains is not None:
            self._v_brains = brains

        self.updateBrains()

    def _initschema( self ):
        self.schema   = {}  # mapping from attribute name to column number
        self.names    = ()  # sequence of column names
        self.indexes  = {}  # maping from index name to index type

        self.insert_patterns = {}  # SQL extension insert patterns
        self.update_patterns = {}  # SQL extension update patterns

    def __len__( self ):
        # Returns catalog (root) size
        return self.getSize()

    def __setstate__( self, state ):
        """
            Initialize your brains. This method is called when the catalog is first 
            activated (from the persistent storage)
        """
        Persistent.__setstate__(self, state)
        self.updateBrains()

    def updateBrains( self ):
        self.useBrains( self._v_brains )

    def setPattern( self, table, columns ):
        #
        # Set *insert* and *update* metadata SQL patterns
        #
        self.insert_patterns[table] = view( self, 'insert_pattern', table=table )

        if type(columns) != type([]):
            columns = [columns]
        for name in columns:
            self.update_patterns[name] = view( self, 'update_pattern', table=table, name=name )
        #
        # Save the new instance state
        #
        self._p_changed = 1

    def delPattern( self, table ):
        #
        # Remove any *insert* SQL patterns
        #
        p = self.insert_patterns
        if p.has_key(table):
            del p[table]
        self.insert_patterns = p
        #
        # Remove any *delete* SQL patterns
        #
        p = self.update_patterns
        if p.has_key(table):
            del p[table]
        self.update_patterns = p
        #
        # Save the new instance state
        #
        self._p_changed = 1

    def useBrains( self, brains ):
        """
            Sets up the Catalog to return an object (ala ZTables) that is created on the 
            fly from the tuple stored in the self.data Btree
        """
        class mybrains( AbstractCatalogBrain, brains ):
            pass

        scopy = {}
        for x in self.schema.keys():
            scopy[x] = self.schema[x][0]

        l = len(self.schema.keys())

        scopy['data_record_id_'] = l
        scopy['data_record_score_'] = l+1
        scopy['data_record_normalized_score_'] = l+2
        scopy['data_record_uid_'] = l+3
        scopy['data_record_path_'] = l+4
        scopy['data_record_childs_'] = l+5

        mybrains.__record_schema__ = scopy

        self._v_brains = brains
        self._v_result_class = mybrains
    #
    #   SQLDB functions ==========================================================================================
    #
    def setup( self ):
        #
        # Initialize catalog SQL database
        #
        if self.getSqlDBName():
            run( self, 'init_db', clear=1 )
        #
        # Initialize SQL tables
        #
        run( self, 'init_root', name=aq_parent(self).sql_root )
        #
        # Default check
        #
        self.check()

    def check( self ):
        #
        # Catalog *default columns* check
        #
        root = aq_parent(self).getSqlRootName()
        columns = view( self, 'default_root_column_ids' )

        indexes = self.indexes or {}
        for name in columns:
            if not name in indexes.keys():
                indexes[name] = ( 0, root, 0, "'", 0, None, None )
        self.indexes = indexes

        self.setPattern( root, columns )

    def _checkSchema( self ):
        #
        # Catalog *schema* check
        #
        catalog_metadata = getattr(self.aq_parent, '_catalog_metadata', None)
        if not catalog_metadata:
            return

        default_columns = view( self, 'default_root_column_ids' )
        names = list(self.names)
        schema = self.schema

        for key, values in self.schema.items():
            if key in default_columns or not catalog_metadata.has_key(key):
                continue

            ext_type, as_root, IsMetatype, indexable, s1, s2, s3, engine = catalog_metadata[key]
            try:
                extTable, extIsIndexable, extType, extComma, extSize = view( self, 'extension_data', name=key )
            except:
                parent = self.aq_parent
                if hasattr(parent, 'delMetaColumn'):
                    parent.delMetaColumn( key, setup=1 )
                if key in names:
                    names.remove(key)
                if schema.has_key(key):
                    del schema[key]
                continue

            i = values[0]
            none = not 'NOT NULL' in s3.upper() and 1 or 0
            schema[key] = ( i, extTable, extType, extComma, none, extSize, engine )

            if key not in names: names.append(key)

        self.names = tuple(names)
        self.schema = schema
        #
        # Save the new instance state
        #
        self._p_changed = 1

    def _checkIndexes( self ):
        #
        # Catalog *indexes* check
        #
        catalog_metadata = getattr(self.aq_parent, '_catalog_metadata', None)
        if not catalog_metadata:
            return

        default_columns = view( self, 'default_root_column_ids' )
        indexes = self.indexes

        for key, values in self.indexes.items():
            if key in default_columns or not catalog_metadata.has_key(key):
                continue

            ext_type, as_root, IsMetatype, indexable, s1, s2, s3, engine = catalog_metadata[key]
            try:
                extTable, extIsIndexable, extType, extComma, extSize = view( self, 'extension_data', name=key )
                idxTable, idxExtType = view( self, 'index_data', name=key )
            except:
                parent = self.aq_parent
                if hasattr(parent, 'delMetaColumn'):
                    parent.delMetaColumn( key, setup=1 )
                if indexes.has_key(key):
                    del indexes[key]
                continue

            hasFullTextIndex = 'FULLTEXT' in view( self, 'indexType', table=idxTable ) and 1 or 0
            none = not 'NOT NULL' in s3.upper() and 1 or 0
            indexes[key] = ( 0, idxTable, extType, extComma, none, extSize, engine, hasFullTextIndex )

        self.indexes = indexes
        #
        # Save the new instance state
        #
        self._p_changed = 1

    def clear( self ):
        """
            Clear catalog
        """
        run( self, 'clear' )

    def drop( self ):
        """
            Drop catalog
        """
        logger.info('drop instance: %s' % self.getId())
        run( self, 'drop' )

    def getData( self, rid ):
        return view( self, 'metadata', rid=rid )

    def getIndexData( self, rid, name=None, default=None ):
        query_items = name and [name] or None
        return view( self, 'metadata', rid=rid, query_items=query_items, for_indexes=1 )

    def getRid( self, uid, check=None ):
        rid = run( self, 'rid', uid=uid, mode='item' )
        if check and not rid:
            rid = run( self, 'rid', path=uid, mode='item' )
        return rid

    def getUids( self, path=None, rid=None ):
        rs = run( self, 'uids', path=path, rid=rid, mode='list' )
        if not rs or type(rs) not in SequenceTypes:
            return None
        return rs

    def getPaths( self, uid=None, rid=None ):
        rs = run( self, 'paths', uid=uid, rid=rid, mode='list', max_rows=1000000 )
        if not rs or type(rs) not in SequenceTypes:
            return None
        return len(rs) == 1 and rs[0] or rs

    def getSize( self ):
        try: return view( self, 'size' ) or 0
        except: return 0
    #
    #   Catalog construction =====================================================================================
    #
    def addColumn( self, name, ext_type, ext_spec, default_value=None, as_root=None, engine=None, \
                   indexable=None, check=None ):
        """
            Adds a row (extension) to the meta data schema
        """
        if not name:
            raise CatalogError, 'Name of index is empty'
        if name[0] == '_':
            raise CatalogError, 'Cannot cache fields beginning with "_"'

        if self.schema.has_key(name) and not check:
            logger.error('addColumn attempted to add existent column %s.' % str(name))
            return

        logger.info('%s.addColumn name: %s, check: %s' % ( self.getId(), name, check ))

        schema = self.schema
        names = list(self.names)

        #if schema.has_key(name):
        #    raise CatalogError, 'The column %s already exists' % name
        #if default_value is None or default_value == '':
        #    default_value = MV

        if not check:
            run( self, 'add_extension', name=name, ext_type=ext_type, ext_spec=ext_spec, as_root=as_root, \
                default_value=default_value, engine=engine, indexable=indexable )

        extTable, extIsIndexable, extType, extComma, extSize = view( self, 'extension_data', name=name )
        none = not 'NOT NULL' in ext_spec.upper() and 1 or 0

        if not schema.has_key(name):
            # schema: ( <index>, <extension table>, <extension type>, <comma>, <size> )
            if schema.values():
                values = [ x[0] for x in schema.values() ]
                if values:
                    i = max(values) + 1
                else:
                    i = 0
            else:
                i = 0
            schema[name] = ( i, extTable, extType, extComma, none, extSize, engine )
            names.append(name)

        self.names = tuple(names)
        self.schema = schema

        self.setPattern( extTable, name )

        if indexable:
            # indexes: ( <empty index>, <index table>, <extension type>, <comma> )
            idxTable, idxExtType = view( self, 'index_data', name=name )
            indexes = self.indexes
            hasFullTextIndex = indexable == 2 and 1 or 0
            indexes[name] = ( 0, idxTable, extType, extComma, none, extSize, engine, hasFullTextIndex )
            self.indexes = indexes

        self.updateBrains() # update the brains
        #
        # Save the new instance state
        #
        self._p_changed = 1

    def delColumn( self, name, check=None ):
        """
            Deletes a row (extension) from the meta data schema
        """
        if not name:
            raise CatalogError, 'Name of index is empty'

        #if not self.schema.has_key(name) and not check:
        #    logger.error('delColumn attempted to delete nonexistent column %s.' % str(name))
        #    return

        logger.info('%s.delColumn name: %s, check: %s' % ( self.getId(), name, check ))

        names = list(self.names)
        _index = names.index(name)

        extTable, extIsIndexable, extType, extComma, extSize = view( self, 'extension_data', name=name )

        if not check:
            try:
                run( self, 'remove_extension', name=name, no_raise=1 )
            except:
                pass

        # rebuild the catalog schema
        schema = self.schema
        del schema[name]
        del names[_index]
        i = 0
        for name in names:
            schema[name] = ( i, ) + tuple(schema[name][1:])
            i += 1

        self.schema = schema
        self.names = tuple(names)

        if extTable == aq_parent(self).getSqlRootName():
            self.setPattern( extTable, name )
        else:
            self.delPattern( extTable )

        if name in self.indexes.keys():
            indexes = self.indexes
            del indexes[name]
            self.indexes = indexes

        self.updateBrains() # update the brains
        #
        # Save the new instance state
        #
        self._p_changed = 1

    def addIndex( self, name, ext_type, ext_spec, default_value=None, as_root=None, engine=None, \
                  indexable=None, check=None ):
        """
            Create a new index, given a name and a index_type.
        """
        if not name:
            raise CatalogError, 'Name of index is empty'

        if self.indexes.has_key(name) and not check:
            logger.error('addIndex attempted to add existent index %s.' % str(name))
            return

        logger.info('%s.addIndex name: %s, check: %s' % ( self.getId(), name, check ))

        if not check:
            run( self, 'add_index', name=name, ext_type=ext_type, ext_spec=ext_spec, as_root=as_root, \
                default_value=default_value, engine=engine, indexable=indexable )

        extTable, extIsIndexable, extType, extComma, extSize = view( self, 'extension_data', name=name )

        idxTable, idxExtType = view( self, 'index_data', name=name )

        self.setPattern( extTable, name )

        indexes = self.indexes
        hasFullTextIndex = indexable == 2 and 1 or 0
        none = not 'NOT NULL' in ext_spec.upper() and 1 or 0
        indexes[name] = ( 0, idxTable, extType, extComma, none, extSize, engine, hasFullTextIndex )
        self.indexes = indexes
        #
        # Save the new instance state
        #
        self._p_changed = 1

    def delIndex( self, name, check=None ):
        """
            Deletes an index
        """
        if not name:
            raise CatalogError, 'Name of index is empty'

        #if not self.indexes.has_key(name) and not check:
        #    logger.error('delIndex attempted to add nonexistent index %s.' % str(name))
        #    return

        logger.info('%s.delIndex name: %s, check: %s' % ( self.getId(), name, check ))

        idxTable, idxExtType = view( self, 'index_data', name=name )

        if not check:
            try:
                run( self, 'remove_index', name=name, no_raise=1 )
            except:
                pass

        if name in self.indexes.keys():
            indexes = self.indexes
            del indexes[name]
            self.indexes = indexes
        #
        # Save the new instance state
        #
            self._p_changed = 1

        # Drop only if not metadata
        if idxTable == aq_parent(self).getSqlRootName() or name in self.names:
            self.setPattern( idxTable, name )
        else:
            self.delPattern( idxTable )

    ### Express Suite DMS cataloging API ###

    def initThread( self, REQUEST, p_log=None ):
        """
            Inits catalog changed log
        """
        setattr(self, '_v_changed', [ REQUEST.get('URL'), {}, 0, 0 ])
        setattr(self, '_v_moved', {})
        self._v_log = p_log
        if not self._IsDebug():
            pass
        elif IsDebug:
            LOG('%s.initThread' % self.getId(), DEBUG, '_v_changed: %s' % self._v_changed)
        else:
            logger.info('%s.initThread: %s' % ( self.getId(), self._v_changed ) )
        return 1

    def isThreadActivated( self ):
        return getattr(self, '_v_changed', None) and 1 or 0

    def isThreadLogged( self ):
        return getattr(self, '_v_log', None) and 1 or 0

    def termThread( self ):
        """
            Terminates catalog index log
        """
        if self.isThreadActivated():
            if len(self._v_changed) == 4 and self._v_changed[2] > 0:
                if not self._IsDebug():
                    pass
                elif IsDebug:
                    LOG('%s.termThread' % self.getId(), DEBUG, 'actions: %s-%s' % ( \
                        self._v_changed[2], self._v_changed[3] ))
                else:
                    logger.info('%s.termThread: actions: %s-%s' % ( \
                        self.getId(), self._v_changed[2], self._v_changed[3] ) )
        setattr(self, '_v_changed', None)
        setattr(self, '_v_moved', None)
        self._v_log = None
        return 1

    def _print_log( self ):
        """
            Prints catalog index log
        """
        if not ( self.isThreadLogged() and self._IsDebug() ):
            return
        catalog_id = self.getId()
        if self._v_moved:
            moved = self._v_moved
            s='\n'
            for path in moved.keys():
                s += '>%s: %s\n' % ( path, str(moved[path]) )
            if IsDebug:
                LOG('%s.commitThread' % catalog_id, DEBUG, 'moved objects:\n%s' % s )
            else:
                logger.info('%s.commitThread moved objects:\n%s' % ( catalog_id, s ))
        if self._v_changed[1]:
            actions = self._v_changed[1]
            s='\n'
            for uid in actions.keys():
                s += '%s:\n' % uid
                action = actions.get( uid, None )
                for x in action:
                    s += '>%s\n' % str(x)
            if IsDebug:
                LOG('%s.commitThread' % catalog_id, DEBUG, 'actions: %s-%s' % ( self._v_changed[0], s ))
            else:
                logger.info('%s.commitThread: actions: %s%s' % ( catalog_id, self._v_changed[0], s ))

    def commitThread( self, REQUEST ):
        """
            Perfoms actions via catalog index log
        """
        catalog_id = self.getId()
        if not getattr(self, '_v_changed', None):
            if not self.isThreadLogged():
                if not self._IsDebug():
                    pass
                elif IsDebug:
                    LOG('%s.commitThread' % catalog_id, DEBUG, 'changed log is empty')
                else:
                    logger.info('%s.commitThread: changed log is empty' % catalog_id)
            return 0

        if REQUEST.get('URL') != self._v_changed[0]:
            logger.error('%s.commitThread: nonunique URLs:\n>%s\n>%s' % ( \
                catalog_id, REQUEST.get('URL'), self._v_changed[0] ))

        actions = self._v_changed[1]
        if not actions:
            self.termThread()
            return 1

        # check moved objects
        moved = getattr(self, '_v_moved', None) or {}
        for path in moved.keys():
            if not actions.has_key(path):
                continue
            uid, object = moved[path]
            a = [ (x[0], x[1], object, x[3]) for x in actions.get(path, []) ]
            if actions.has_key(uid):
                actions[ uid ].extend( a )
            else:
                actions[ uid ] = a
            del actions[ path ]

        self._print_log()

        for uid in actions.keys():
            action = actions.get( uid, None )
            if not action:
                logger.error("%s.commitThread: action is None: [%s]" % ( catalog_id, uid ))
                continue

            action.sort()
            IsUncatalog = IsCatalog = 0
            idxs = []
            ob = None

            for date, op, object, indexes in action:
                if op == 'u':
                    IsUncatalog = 1
                    break
                elif op == 'c':
                    if object is None:
                        logger.error("%s.commitThread: object is None: [%s]" % ( catalog_id, uid ))
                        continue

                    if ob is None or ob is not object:
                        ob = object
                    if indexes:
                        idxs.extend( [ x for x in indexes if x not in idxs ] )
                    elif 'all' not in idxs:
                        idxs.append( 'all' )
                    IsCatalog = 1

            if IsUncatalog:
                self.uncatalogObject( uid, force=1 )
                if not self.isThreadLogged():
                    if not self._IsDebug():
                        pass
                    elif IsDebug:
                        LOG('%s.commitThread' % catalog_id, DEBUG, 'uncatalog object: [%s]' % uid)
                    else:
                        logger.info('%s.commitThread: uncatalog object: [%s]' % ( catalog_id, uid ))

            elif IsCatalog:
                total = self.catalogObject( ob, uid, idxs=idxs, force=1 )
                if not self.isThreadLogged():
                    if not self._IsDebug():
                        pass
                    elif IsDebug:
                        LOG('%s.commitThread' % catalog_id, DEBUG, "catalog object: %s, indexes %s, total %s" % ( \
                            uid, str(idxs), total ))
                    else:
                        logger.info("%s.commitThread: catalog object: [%s], indexes %s, total %s" % ( \
                            catalog_id, uid, str(idxs), total ))

            self._v_changed[3] += 1

        self.termThread()
        return 1

    def updateMetadata( self, object, uid, rid=None, force=None, check=None ):
        """
            Given an object and a uid, update the column data for the uid with the object
            data if the object has changed
        """
        x = self.recordify( object, uid, rid )

        if rid is None:
            newDataRecord = x
            try:
                path = '/'.join(object.getPhysicalPath())
            except:
                path = None
            idxs = None
            run( self, 'append', metadata=newDataRecord, uid=uid, path=path )
            rid = self.getRid( uid )
            if IsDebug:
                LOG('%s.updateMetadata' % self.getId(), DEBUG, 'new RID:%s' % rid)

        elif x or force:
            updatedDataRecord, idxs = x
            run( self, 'update', metadata=updatedDataRecord, rid=rid, uid=uid )
            if IsDebug:
                LOG('%s.updateMetadata' % self.getId(), DEBUG, 'updated RID:%s' % rid)

        return check and ( rid, idxs, ) or rid

    ### ZSQLCatalog cataloging API ###

    def catalogObject( self, object, uid, threshold=None, idxs=None, update_metadata=1, force=None ):
        """
            Adds an object to the Catalog by iteratively applying it to all indexes.

            Arguments:

                'object' is the object to be cataloged

                'uid' is the unique Catalog identifier for this object

                'force' is flag indicated of forced running.

            If 'idxs' is specified (as a sequence), apply the object only to the named indexes.

            If 'update_metadata' is true (the default), also update metadata for the object.
            If the object is new to the catalog, this flag has no effect (metadata is
            always created for new objects).
        """
        try:
            if aq_parent(self)._check_unindexable_content(object):
                return 0
        except:
            pass

        if not force and self.isThreadActivated():
            actions = self._v_changed[1]
            if not actions.has_key(uid):
                actions[ uid ] = []

            if idxs:
                if type(idxs) is types.StringType:
                    use_indexes = [ idxs ]
                elif type(idxs) is types.TupleType:
                    use_indexes = list(idxs)
                else:
                    use_indexes = idxs
            else:
                use_indexes = []

            actions[ uid ].append( ( DateTime(), 'c', object, use_indexes ) )
            self._v_changed[1] = actions
            self._v_changed[2] += 1

            return 0

        catalog_id = self.getId()

        try:
            oid = object.getId()
        except:
            oid = None
        if not self._IsDebug():
            pass
        elif IsDebug:
            LOG('%s.catalogObject' % catalog_id, DEBUG, "catalogObject index object, id: %s" % oid)
        else:
            logger.info('%s.catalogObject index object, id: %s' % ( catalog_id, oid ))

        rid = self.getRid( uid )
        use_indexes = idxs and idxs[:] or []
        checked = None

        if not idxs or 'all' in use_indexes:
            use_indexes.extend( [ x for x in self.indexes.keys() if not x in use_indexes ] )
            try:
                use_indexes.remove( 'all' )
            except:
                pass

        # Update metadata and automatically make implicit indexes

        if rid is None:
            # we are inserting new data
            rid = self.updateMetadata( object, uid )
            use_indexes = [ x for x in use_indexes if not x in self.names ]
        elif update_metadata:
            # we are updating and we need to update metadata
            checked = self.updateMetadata( object, uid, rid, check=1 )
            use_indexes = [ x for x in use_indexes if not x in self.names ]
        else:
            # we don't update metadata at all
            pass

        # Check and optimize explicit indexes list

        if self.isThreadActivated() and checked:
            if checked[0] != rid:
                logger.info('%s.catalogObject checked rid invalid, rid:%s-%s' % ( catalog_id, rid, checked ))
            else:
                r, i = checked
                if i and use_indexes != i and len(i) < len(use_indexes):
                    if hasattr(self, 'explicitIndexes'):
                        for x in self.explicitIndexes():
                            if not x in idxs and x in i:
                                i.remove( x )
                            elif x in idxs and not x in i:
                                i.append( x )
                    if IsDebug:
                        LOG('%s.catalogObject' % catalog_id, DEBUG, 'idxs optimized, rid:%s-%s, idxs:%s' % ( \
                            rid, i, use_indexes ))
                    use_indexes = i
            del checked

        if not rid:
            logger.error("%s.catalogObject NOT RID, uid: %s" % ( catalog_id, uid ))
            return 0

        if use_indexes:

            # Update explicit indexes only

            keys = self.indexes.keys()
            total = 0

            for name in use_indexes:
                if not name or name not in keys:
                    #if IsDebug:
                    #    logger.error('%s.catalogObject was passed bad index: [%s]' % ( catalog_id, name ))
                    continue
                value = self.getObjectAttrValue( object, name )
                run( self, 'apply_index', rid=rid, key=name, value=value )
                total += 1

        else:
            total = 1

        if not self._IsDebug():
            pass
        elif IsDebug:
            LOG('%s.catalogObject' % catalog_id, DEBUG, "(!) uid: %s\nindexes: %s\nrid: %s" % ( \
                uid, str(use_indexes), rid ))
        else:
            logger.info("%s.catalogObject uid: %s" % ( catalog_id, uid ))

        return total

    def moveObject( self, object, uid, path, idxs=None, force=None ):
        """
            Move object inside the catalog:

            Arguments:

                'object' -- is the object to be cataloged

                'uid' -- new object location (current path)

                'path' -- old location (path/uid in the catalog)

                'idxs' -- indexes name list or tuple.
        """
        if not force and self.isThreadActivated():
            self._v_moved[ path ] = ( uid, object, )

        rid = self.getRid( path )
        if not rid:
            return 0

        catalog_id = self.getId()
        columns = view( self, 'default_root_column_ids' )
        total = 0

        for name in columns:
            if not name in ( 'uid', 'path', ):
                continue
            run( self, 'apply_index', rid=rid, key=name, value=uid )
            total += 1

        if idxs is None:
            use_indexes = ( 'parent_path', )
        else:
            use_indexes = idxs

        for name in use_indexes:
            if not name in self.indexes:
                continue
            value = self.getObjectAttrValue( object, name )
            run( self, 'apply_index', rid=rid, key=name, value=value )
            total += 1

        if IsDebug:
            LOG('%s.moveObject' % catalog_id, DEBUG, "(!) uid: %s\nindexes: %s\nrid: %s" % ( \
                uid, str(use_indexes), rid ))

        return total

    def uncatalogObject( self, uid, force=None ):
        """
            Uncatalog and object from the Catalog.  and 'uid' is a unique Catalog identifier.

            Note, the uid must be the same as when the object was catalogued, otherwise it will
            not get removed from the catalog. This method should not raise an exception if
            the uid cannot be found in the catalog.
        """
        if not force and self.isThreadActivated():
            actions = self._v_changed[1]
            if not actions.has_key(uid):
                actions[ uid ] = []

            actions[ uid ].append( ( DateTime(), 'u', None, None ) )
            self._v_changed[1] = actions
            self._v_changed[2] += 1
            return 0

        catalog_id = self.getId()

        rid = self.getRid( uid, check=1 )

        if rid is None:
            return 1

        if not self._IsDebug():
            pass
        elif IsDebug:
            LOG('%s.uncatalogObject' % catalog_id, DEBUG, "uid: %s\nrid: %s" % ( uid, rid ))
        else:
            logger.info('%s.uncatalogObject uid: %s\nrid: %s' % ( catalog_id, uid, rid ))

        run( self, 'remove', rid=rid )

        if not self._IsDebug():
            pass
        elif IsDebug:
            LOG('%s.uncatalogObject' % catalog_id, DEBUG, "uid: %s" % uid)
        else:
            logger.info("%s.uncatalogObject uid: %s" % ( catalog_id, uid ))

        return 1

    def uniqueValuesFor( self, name ):
        """
            Returns unique values for FieldIndex name
        """
        pass #return self.getIndexData( name=name ).uniqueValues()

    def hasUid( self, uid ):
        """
            Returns the rid if catalog contains an object with uid
        """
        return self.getRid( uid )

    def getObjectAttrValue( self, object, attr, sort=None ):
        """
            Returns object attr value
        """
        ob = object
        # check attribute inheritted value by 'getBase' function
        while ob is not None:
            v = getattr(ob, attr, MV)
            if v is not MV or not IsCheckBase or not hasattr(ob, 'getBase'):
                break
            try:
                ob = self.wrapOb(ob.getBase())
            except:
                break
        if v is not MV and safe_callable(v):
            try:
                v = v()
            except AttributeError:
                if attr == 'parent_path':
                    #return aq_parent(object).getPhysicalPath()
                    return None
        if sort and type(v) in SequenceTypes:
            v.sort()
        return v

    def IsEqual( self, v1, v2 ):
        t = type(v1)
        if t != type(v2):
            return 0
        if ( v1 == v2 or not ( v1 or v2 ) ):
            return 1
        if t is type(DateTime()):
            f = SQLParser.datetime_format
            if v1.strftime(f) == v2.strftime(f): return 1
        elif t is types.ListType:
            v1.sort()
            v2.sort()
            if v1 == v2: return 1
        elif t is types.TupleType:
            if v1 == v2: return 1
        elif t is types.DictType:
            #v1.sort( lambda x, y: cmp(x, y) )
            #v2.sort( lambda x, y: cmp(x, y) )
            if v1 == v2: return 1
        else:
            if str(v1) == str(v2): return 1
        return 0

    def recordify( self, object, uid=None, rid=None ):
        """
            Turns an object into a record tuple
        """
        record = []
        data = []
        if rid:
            if uid and rid == self.getRid( uid ):
                data = self.getData(rid)
            else:
                if IsDebug:
                    LOG('%s.recordify' % self.getId(), DEBUG, 'rid is not valid, uid: %s' % uid)
            check = data and 1 or 0
            idxs = self.indexes.keys()
        else:
            check = 0

        # check metadata identical
        for x in self.names:
            value = self.getObjectAttrValue( object, x )
            n = self.schema[x][0]
            if check:
                v = data[n]
                if self.IsEqual( v, value ):
                    value = MV
                    if x in idxs:
                        idxs.remove( x )
            record.append( value )

        if not check:
            return tuple(record)
        if 1 or not ( rid and self.isThreadActivated() ): # XXX getIndexData
            return ( tuple(record), idxs, )

        # check explicit indexes data identical
        indexes = [ x for x in self.indexes.keys() if not x in self.names ]
        data = self.getIndexDataForRID( rid, default=MV, explicit=1 )

        for x in indexes:
            if x == 'path':
                value = '/'.join(object.getPhysicalPath())
            else:
                value = self.getObjectAttrValue( object, x )
            try:
                n = self.schema[x][0]
                v = data[n]
            except:
                continue
            try:
                if value is MV: continue
                if self.IsEqual( v, value ) and x in idxs:
                    idxs.remove( x )
            except:
                pass

        return ( tuple(record), idxs, )

    def instantiate( self, record ):
        r = self._v_result_class( record[1] )
        r.data_record_id_ = record[0]
        r.data_record_uid_ = record[2]
        r.data_record_path_ = record[3]
        r.data_record_childs_ = record[4]
        return r.__of__(self)

    def getMetadataForRID( self, rid ):
        record = self.getData(rid)
        result = {}
        for ( key, x ) in self.schema.items():
            result[key] = record[x[0]]
        return result

    def getIndexDataForRID( self, rid, default="", explicit=None ):
        return self.getIndexData(rid)

    ## This is the Catalog search engine. Most of the heavy lifting happens below

    def _apply_index( self, key, request ):
        """
            Returns parsed query of the given index
        """
        x = request.items( [key] )
        if not x:
            return None
        try: idx = tuple(self.indexes[key][1:])
        except: idx = ( None, 0, "'", 0, 0, '', 0 )
        return x[0]+idx

    def _parse_query( self, request ):
        # Returns parsed search query
        query = []
        for k in self.indexes.keys():
            idx = self._apply_index( k, request )
            if not idx: continue
            query.append( idx )
        return query

    def _lazify_results( self, rs ):
        # Returns searched brains
        if rs is not None:
            #rs = self.checkTraverse( rs, limit )
            rs = LazyMap( self.instantiate, rs, len(rs) )
            #rs = LazyMap( self.__getitem__, rs, len(rs) )
        else:
            rs = LazyCat([])
        return rs

    def _get_sort_attr( self, attr, kw ):
        """
            Helper function to find sort-on or sort-order
        """
        # There are three different ways to find the attribute:
        # 1. kw[sort-attr]
        # 2. self.sort-attr
        # 3. kw[sort_attr]
        # kw may be a dict or an ExtensionClass MultiMapping, which
        # differ in what get() returns with no default value.
        name = "sort-%s" % attr
        val = kw.get(name, None)
        if val is not None:
            return val
        val = getattr(self, name, None)
        if val is not None:
            return val
        return kw.get("sort_%s" % attr, None)

    def _getSortIndex( self, args ):
        """
            Returns a search index object or None
        """
        sort_index_name = self._get_sort_attr("on", args)
        if sort_index_name in aq_parent(self).getRootIndexes():
            return sort_index_name
        elif sort_index_name is not None:
            sort_index = self.indexes.get(sort_index_name)
            if sort_index is None:
                return None
            return sort_index_name
        else:
            return None

    def count( self, request ):
        """
            Returns counter of records matched the query
        """
        # Parsed query
        query = self._parse_query( request )

        if not self._IsDebug():
            pass
        elif IsDebug:
            LOG('%s.count' % self.getId(), DEBUG, 'query:\n%s' % query)
        else:
            logger.info('%s.count: - start, query:\n%s' % ( self.getId(), query ))

        # We should return here counter only
        total_objects = view( self, 'size', query=query )

        if not self._IsDebug():
            pass
        elif IsDebug:
            LOG('%s.count' % self.getId(), DEBUG, 'total_objects: %s' % total_objects)
        else:
            logger.info('%s.count: - total_objects: %s' % ( self.getId(), total_objects ))

        return total_objects or 0

    def countResults( self, REQUEST=None, **kw ):
        # Count results matching the query
        if REQUEST is None and not kw:
            # Try to acquire request if we get no args for bw compat
            REQUEST = getattr(self, 'REQUEST', None)
        return self.count( CatalogSearchArgumentsMap(REQUEST, kw) )

    def trees( self, request ):
        """
            Returns searched trees matched the query as a Lazified record set
        """
        IsDebug = self._IsDebug()
        
        # Parsed custom query
        query = self._parse_query( request )
        requested_path = request.get('path').replace('%', '')
        # Expanded tree's nodes
        expanded = request.get('expanded') or []
        # Trees sort index
        sort_index = 'path'

        if IsDebug:
            LOG('%s.trees' % self.getId(), DEBUG, 'query: %s\nexpanded %s\nrequested_path: %s' % ( \
                query, expanded, requested_path ))

        # Get matched trees
        trees = view( self, 'trees', query=query )

        if not trees: return []

        if IsDebug:
            LOG('%s.trees' % self.getId(), DEBUG, 'trees:\n%s' % '\n'.join([ x[1] for x in trees ]))

        rs = {}
        parents = ['/']
        max_level = 2
        extra_level = 0
        level = 0
        for rid, path, parent in trees:
            if requested_path:
                if path != requested_path and not path.startswith(requested_path+'/'):
                    continue
            add = 0
            # set current level
            p = parents[0]
            l = len(parent.split('/')) - 2
            # it's current level
            if p == parent:
                pass
            # down
            elif p in parent and l == level + 1:
                parents.insert( 0, parent )
                pass
            # extra, item on the more deeper level (allowed by roles)
            elif parent not in parents:
                #parents.insert( 0, parent )
                extra_level = l
            # up
            else:
                while parents[0] != parent:
                    parents.pop(0)
            # parse (include in the results) 0,1 levels only or expanded nodes
            if parent in expanded or l < max_level:
                add = 1
            elif extra_level:
                extra_level = 0
                add = 1
            # add new rid or count childs
            if add:
                rs[path] = [ rid, 0 ]
            if rs.has_key(parent):
                rs[parent][1] += 1
            level = l

        #if IsDebug:
        #    LOG('%s.trees' % self.getId(), DEBUG, 'rs: %s' % rs)
        
        # Parsed metadata query
        root = aq_parent(self).getSqlRootName()
        rids = [ x[0] for x in rs.values() ]
        rids.sort()
        query = [ ( 'RID', rids, root, 0, '' ), ]
        # Get only given metadata items (extensions), '[]' - root only
        items = request.get('query_items')

        # We should return here resultset as a tuple (rid, metadata)
        # where 'metadata' is tuple matched the schema
        total_objects, res = view( self, 'search', query=query, items=items, sort_index=sort_index )

        # Set valid childs count
        for x in res:
            path = x[3]
            if not ( rs.has_key(path) and rs[path][1] ):
                continue
            x[4] = rs[path][1]

        # Pack results
        res = self._lazify_results( res )

        if IsDebug:
            LOG('%s.trees' % self.getId(), DEBUG, 'res:\n%s' % '\n'.join([ x.getPath() for x in res ]))

        del parents
        del trees
        del rs

        if IsDebug:
            LOG('%s.trees' % self.getId(), DEBUG, 'total %s, res: %s' % ( total_objects, len(res) ))

        return res

    def searchTrees( self, REQUEST=None, **kw ):
        # Search object trees matching the query
        if REQUEST is None and not kw:
            # Try to acquire request if we get no args for bw compat
            REQUEST = getattr(self, 'REQUEST', None)
        return self.trees( CatalogSearchArgumentsMap(REQUEST, kw) )

    def search( self, request, sort_index=None, reverse=0, limit=None, offset=None, merge=1, rs_type=None ):
        """
            Returns searched items matched the query as a Lazified record set
        """
        # Parsed query
        query = self._parse_query( request )
        # Get only given metadata items (extensions), '[]' - root only
        items = request.get('query_items')

        if not self._IsDebug():
            pass
        elif IsDebug:
            LOG('%s.search' % self.getId(), DEBUG, 'query:\n%s\nsort_index:%s\nitems:%s' % ( \
                query, sort_index, items ))
        else:
            logger.info('search: - start:%s:%s\nquery:\n%s\nitems:%s' % ( \
                rs_type, limit, query, items ))

        # We should return here resultset as a tuple (rid, metadata)
        # where 'metadata' is tuple matched the schema
        total_objects, rs = view( self, 'search', query=query, items=items, sort_index=sort_index, \
                reverse=reverse, limit=limit, offset=offset )

        # Pack results
        rs = self._lazify_results( rs )

        if not self._IsDebug():
            pass
        elif IsDebug:
            LOG('%s.search' % self.getId(), DEBUG, 'end %s:%s, rs:%s' % ( \
                rs_type, total_objects, rs and len(rs) or None ))
        else:
            logger.info('%s.search: - end %s:%s, rs:%s' % ( \
                self.getId(), rs_type, total_objects, \
                rs and len(rs) or None ))

        if rs_type:
            if not total_objects and rs is not None:
                total_objects = len(rs)
            return ( total_objects, rs, )
        else:
            return rs

    def searchResults( self, REQUEST=None, used=None, _merge=1, **kw ):
        # Search results matching the query
        if REQUEST is None and not kw:
            # Try to acquire request if we get no args for bw compat
            REQUEST = getattr(self, 'REQUEST', None)
        #logger.info('searchResults: REQUEST:\n%s\nkw:\n%s' % ( REQUEST, kw ))

        args = CatalogSearchArgumentsMap(REQUEST, kw)
        sort_index = self._getSortIndex(args)
        sort_limit = self._get_sort_attr('limit', args)
        sort_offset = self._get_sort_attr('offset', args)
        rs_type = kw.get('rs_type', 0)

        reverse = 0
        if sort_index is not None:
            order = self._get_sort_attr('order', args)
            if isinstance(order, str) and order.lower() in ('reverse', 'descending'):
                reverse = 1

        # Perform searches with indexes and sort_index
        return self.search( args, sort_index, reverse, sort_limit, sort_offset, _merge, rs_type )

    def checkTraverse( self, rs, limit=None ):
        # Checks valid traversabled limited resultset
        #assert limit is None or limit > 0, 'Limit value must be 1 or greater'
        res = []
        n = 1
        for x in rs:
            if limit and n > limit:
                break
            path = x[3]

            try: IsFound = path and self.unrestrictedTraverse( path ) and 1 or 0
            except: IsFound = 0

            if IsFound:
                res.append( x )
                n += 1
            else:
                LOG('%s.checkTraverse' % self.getId(), INFO, 'path: %s\nx: %s' % ( path, x ))
        return res

    __call__ = searchResults


class CatalogSearchArgumentsMap:
    """
    Multimap catalog arguments coming simultaneously from keywords and request.

    Values that are empty strings are treated as non-existent. This is to ignore empty values,
    thereby ignoring empty form fields to be consistent with hysterical behavior.
    """
    def __init__( self, request, keywords ):
        self.request = request or {}
        self.keywords = keywords or {}

    def __getitem__( self, key ):
        marker = MV
        v = self.keywords.get(key, marker)
        if v is marker or v == '':
            try: v = self.request[key]
            except: v = None
        if v == '':
            raise KeyError(key)
        return v

    def get( self, key, default=None ):
        try:
            v = self[key]
        except KeyError:
            return default
        else:
            return v

    def keys( self ):
        rs = self.keywords.keys()
        for x in self.request.keys():
            if x not in rs:
                rs.append( x )
        return rs

    def items( self, valid_keys=None ):
        return [ ( x, self.get(x) ) for x in self.keys() if not valid_keys or x in valid_keys ]

    def has_key( self, key ):
        try:
            self[key]
        except KeyError:
            return 0
        else:
            return 1


def mergeResults( results, has_sort_keys, reverse ):
    """
        Sort/merge sub-results, generating a flat sequence.
        Results is a list of result set sequences, all with or without sort keys
    """
    if not has_sort_keys:
        return LazyCat(results)
    else:
        # Concatenate the catalog results into one list and sort it
        # Each result record consists of a list of tuples with three values:
        # (sortkey, docid, catalog__getitem__)
        if len(results) > 1:
            all = []
            for r in results:
                all.extend(r)
        elif len(results) == 1:
            all = results[0]
        else:
            return []
        all.sort()
        if reverse:
            all.reverse()
        return LazyMap(lambda rec: rec[2](rec[1]), all, len(all))
