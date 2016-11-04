"""
AttributesIndex.

AttributesIndex class provides document category attributes search/sort
functionality. Though AttributesIndex implements the Pluggable Index interface,
it maintains it's own ZCatalog.

During the object indexing process, document category attributes are
represented as an attribute name to value mapping. Then, a special transient
object is instantiated for each attribute. According to the attribute's type,
it's value is set into the particular transient object's property. Transient
attribute object is then being cataloged and therefore every attribute is
indexed with index according to the predefined schema. While searching for the
attribute values, query is passed to the corresponding index.

$Id: AttributesIndex.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 04/02/2007 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from cgi import escape
from zLOG import LOG, INFO, ERROR
from types import ListType, TupleType, IntType, StringType

from Globals import DTMLFile
from BTrees.IIBTree import IISet, intersection
from BTrees.OOBTree import OOSet

from Globals import PersistentMapping

from Products.PluginIndexes.common.PluggableIndex import PluggableIndexInterface
from Products.PluginIndexes.common.util import parseIndexRequest
from Products.ZCatalog.Catalog import Catalog
from Products.ZCatalog.ZCatalog import ZCatalog

from Config import Permissions
from CatalogTool import CatalogTool
from SimpleObjects import ContainerBase
from Utils import InitializeClass, multiintersection, multiunion


class AttributeObject:

    meta_type = 'AttributeObject'

    def __init__( self, name, value, index_name, record ):
        self.name = name
        self.record = record
        setattr( self, index_name, value )

class AttributesIndex( ContainerBase, ZCatalog ):
    """
        Category attributes index
    """
    _class_version = 1.00

    __implements__ = ( ContainerBase.__implements__,
                       ZCatalog.__implements__,
                       PluggableIndexInterface,
                     )

    meta_type = 'AttributesIndex'

    manage_options = ZCatalog.manage_options

    query_options = ['query', 'operator']
    operators = ['or', 'and']
    default_operator = 'or'

    _catalog_indexes = [ \
                         ('string_value', 'TextIndexNG2'),
                         ('int_value', 'FieldIndex'),
                         ('float_value', 'FieldIndex'),
                         ('currency_value', 'FieldIndex'),
                         ('boolean_value', 'FieldIndex'),
                         ('date_value', 'FieldIndex'),
                         ('list_value', 'FieldIndex'),
                         ('lines_value', 'KeywordIndex'),
                         ('items_value', 'KeywordIndex'),
                         ('userlist_value', 'KeywordIndex'),
                         ('text_value', 'TextIndexNG2'),
                         ('name', 'FieldIndex'),
                         ('record', 'FieldIndex'),
                       ]

    _catalog_metadata = []

    def __init__( self, id, caller=None, ):
        ContainerBase.__init__( self, id )
        self._catalog = Catalog()
        self.attr_schema = PersistentMapping()

    def this( self ):
        return self

    def clear( self ):
        return self._catalog.clear()

    def _instance_onCreate( self ):
        self.setupIndexes( reindex=1, REQUEST=None )

    def enumerateIndexes( self ):
        """
            Returns a list of ( index_name, type, extra ) pairs for the initial index set
        """
        return self._catalog_indexes

    def enumerateColumns( self ):
        """
            Returns a sequence of schema names to be cached
        """
        return self._catalog_metadata

    def setupIndexes( self, reindex=None, REQUEST=None ):
        """
            Configure the catalog indexes settings.

            Arguments:

                'reindex' -- try to reindex new or updated Index.
        """
        reindexed = []

        # Setup new indexes
        for item in self.enumerateIndexes():
            index, typ = item[0:2]
            extra = len(item) == 3 and item[2]
            if index not in self.indexes():
                self.addIndex( index, typ, extra )
                reindexed.append( index )

        if reindex and reindexed:
            for index in reindexed:
                try:
                    self.reindexIndex( index, REQUEST=REQUEST )
                except:
                    raise
                LOG('AttributesIndex.setupIndexes', INFO, "= Index: %s reindexed" % index)

    def getEntryForObject( self, document_id, default=None ):
        """
           Returns all the information we have on that specific object.
        """
        record_idx = self._catalog.getIndex('record')
        attribute_ids = record_idx._index.get( document_id ) or []
        if type( attribute_ids ) is IntType:
            attribute_ids = [ attribute_ids ]
        elif attribute_ids:
            attribute_ids = attribute_ids.keys()

        return [ self._catalog.getIndexDataForRID( id ) for id in attribute_ids ]

    def registerAttribute( self, id, typ ):
        """
            Adds new attribute to the indexing schema.

            Arguments:

                'id' -- Full attribute name in a form '<Category id>.<Attribute id>',
                        e.g. 'Document.field1'.

                'typ' -- Attribute type. According to the given type, an appropriate index
                         will be selected for storing the attribute data.

            Result:

                Returns the name of index associated with given attribute type in case
                an attribute was succesfully registered. Returns None otherwise.
        """
        index_name = '%s_value' % typ

        if self._catalog.indexes.get(index_name) is not None:
            self.attr_schema[ id ] = index_name
            return index_name
        return None

    def unregisterAttribute( self, id ):
        """
            Adds new attribute to the indexing schema.

            Arguments:

                'id' -- Full attribute name in a form '<Category id>.<Attribute id>'.

            Exceptions:

                'KeyError' -- Attribute was not registered in the index schema.
        """
        del self.attr_schema[ id ]

    def getAttributesSchema( self ):
        """
            Returns the attribute indexing schema.

            Result:

                Dictionary. Mapping from attribute name to index name.
        """
        return self.attr_schema

    #
    # Pluggable index interface
    #
    def index_object( self, document_id, obj, threshold=None ):
        category = getattr( obj, 'category', None )
        if category is None or not obj.implements('isCategorial'):
            return 0

        # source = getattr(obj, self.source_name, None)
        source = getattr(obj, self.getId(), None)
        if source is not None:
            try:
                source = source()
            except TypeError:
                pass
            try:
                source = source.items()
            except (TypeError, AttributeError):
                pass
        else:
            return 0

        for attr_name, attr_value in source:
            full_attr_name = "%s/%s" % ( category, attr_name )
            index_name = self.attr_schema.get( full_attr_name )
            if not index_name:
                # Don't know how to handle attribute.
                cdef = obj.getCategory()
                adef = cdef and cdef.getAttributeDefinition( attr_name )
                typ = adef and adef.Type()
                index_name = typ and self.registerAttribute( "%s/%s" % ( category, attr_name ), typ )
                if not index_name:
                    continue

            attr_obj = AttributeObject( name=full_attr_name, value=attr_value, index_name=index_name, record=document_id )
            self.catalog_object( attr_obj, '%s/%s' % ( full_attr_name, document_id ) )

        return 1

    def unindex_object( self, document_id ):
        """
            Find every attribute associated with given document_id and uncatalog it
        """
        attribute_ids = self._catalog.getIndex('record')._index.get( document_id )
        if attribute_ids is None:
            return

        if type( attribute_ids ) is IntType:
            attribute_ids = [ attribute_ids ]
        else:
            attribute_ids = list( attribute_ids.keys() )

        for attr_id in attribute_ids:
            try:
                uid = self._catalog.paths[ attr_id ]
                self.uncatalog_object( uid )
            except: pass

    def _apply_index( self, request, cid='' ):
        """
            Apply the index to query parameters given in the argument
        """
        record = parseIndexRequest(request, self.getId(), self.query_options)
        if record.keys == None: return None

        operator = record.get('operator', self.default_operator)
        if not operator in self.operators:
            raise RuntimeError, "operator not valid: %s" % escape(operator)

        if operator == 'or':
            set_func = multiunion
        else:
            set_func = multiintersection

        keys = record.keys
        if type(keys) is not ListType:
            keys = [keys]

        setlist = OOSet()
        record_idx = self._catalog.getIndex('record')
        for query in keys:
            query = query.copy()
            attributes = query['attributes']
            del query['attributes']

            if type( attributes ) is StringType:
                attributes = [ attributes ]

            # Find out attribues of the same index.
            query_indexes = {}
            for attr_name in attributes:
                index_name = self.attr_schema.get( attr_name )
                if index_name:
                    if not query_indexes.has_key( index_name ):
                        query_indexes[ index_name ] = []
                    query_indexes[ index_name ].append( attr_name )

            document_ids = IISet()
            for index_name, attr_names in query_indexes.items():
                attribute_ids = self.searchAttributes( { 'name': attr_names, index_name: query } )
                document_ids.update( [ record_idx.keyForDocument(id) for id in attribute_ids ] )

            setlist.insert( document_ids )

        r = set_func( setlist )

        if r is None:
            return IISet(), (self.id,)

        if type(r) is IntType:
            return IISet([r]), (self.id,)
        else:
            return r, (self.id,)

    def numObjects( self ):
        """ return number of index objects """
        record_idx = self._catalog.indexes.get('record', None)
        return record_idx is not None and record_idx.numObjects()

    def indexSize( self ):
        """ return size for portal catalog implementing """
        return self.numObjects()

    def searchAttributes( self, REQUEST=None, **kw ):
        """
            Result:

                List of the attribute record ids.
        """
        results = self.searchResults( REQUEST, **kw ) or []
        return [ r.getRID() for r in results ]

    def getSortIndex( self, args ):
        """
            Returns a transient index object suitable for sorting on the particular attribute.
        """
        attr_name = self._catalog._get_sort_attr( "attr", args )

        value_index_name = self.attr_schema.get( attr_name )
        return attr_name and TransientSortIndex( attr_name,
                                                 self._catalog.getIndex(value_index_name),
                                                 self._catalog.getIndex('record'),
                                                 self._catalog.getIndex('name')
                                               )

InitializeClass( AttributesIndex )


class TransientSortIndex:

    def __init__( self, name, value_index, record_index, name_index ):
        self.name = name
        self.value_index = value_index
        self.record_index = record_index
        self.name_index = name_index

        # Store record ids of all AttributeObjects which are associated with the
        # given attribute name.
        self.attribute_ids = name_index._index[ name ]

    def __getattr__( self, attr ):
        if  attr == 'keyForDocument' \
            and hasattr( self.value_index, 'keyForDocument' ):
            return self._keyForDocument
        raise AttributeError, attr

    def _keyForDocument( self, id ):
        intset = intersection( self.record_index._index[ id ], self.attribute_ids )
        return self.value_index.keyForDocument( intset[0] )

    def items( self ):
        _value_index_keyForDocument = self.value_index.keyForDocument
        _record_index_keyForDocument = self.record_index.keyForDocument
        return [ ( _value_index_keyForDocument( id ), _record_index_keyForDocument( id ) ) for id in self.attribute_ids.keys() ]

    def __len__( self ):
        return len( self.attribute_ids )


manage_addAttributesIndexForm = DTMLFile('dtml/addAttributesIndex', globals())


def manage_addAttributesIndex( self, id, REQUEST=None, RESPONSE=None, URL3=None ):
    """
        Add a field index
    """
    return self.manage_addIndex( id, 'AttributesIndex', extra=None, \
             REQUEST=REQUEST, RESPONSE=RESPONSE, URL1=URL3 )


#def initialize( context ):
#    # module initialization callback

#    context.registerClass(
#        AttributesIndex,
#        permission   = Permissions.AddPluggableIndex,
#        constructors = (manage_addAttributesIndexForm, manage_addAttributesIndex),
#        visibility   = None,
#    )
