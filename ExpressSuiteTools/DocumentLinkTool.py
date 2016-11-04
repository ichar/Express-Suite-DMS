"""
Basic searchable catalog and storage for links between the documents
$Id: DocumentLinkTool.py, v 1.0 2007/08/30 12:00:00 Exp $

*** Checked 13/06/2009 ***

"""
__version__ = '$Revision: 1.0 $'[11:-2]

from Acquisition import Implicit, aq_base
from AccessControl import Permissions as ZopePermissions
from AccessControl import ClassSecurityInfo, Owned, Role
from zExceptions import Unauthorized

from Products.CMFCore import permissions as CMFCorePermissions
from Products.CMFCore.ActionProviderBase import ActionProviderBase
from Products.CMFCore.CMFCatalogAware import CMFCatalogAware
from Products.CMFCore.utils import getToolByName, _getAuthenticatedUser, _checkPermission

from OFS.ObjectManager import ObjectManager
from OFS.SimpleItem import Item

from random import random
from types import StringType, DictType
from DateTime import DateTime

from Config import DocumentLinkProperties, Roles
from CatalogTool import CatalogTool
from SimpleObjects import Persistent

from Utils import InitializeClass, listClipboardObjects, getObjectByUid, getClientStorageType, \
     addQueryString, get_param

from logging import getLogger
logger = getLogger( 'DocumentLinkTool' )


class Link( Persistent, Implicit, Item, Role.RoleManager ):
    """
        Link represents some relation between two document items.
    """
    _class_version = 1.0

    __allow_access_to_unprotected_subobjects__ = 1

    meta_type = 'Link'

    security = ClassSecurityInfo()

    def __init__( self, id, sourceObject, destinationObject, relation_type, relation_direction, extra=None ):
        """
            Creates persistent link between sourceObject and destinationObject.

            Arguments:

                'sourceObject' -- object from which the link is originated

                'destinationObject' -- object to which the link is pointed

                'relation_type' -- type of relationship between the sourse and
                    the destination objects (0 or 1)

                'relation_direction' -- the direction if link (0 - from sourse to
                    destination and 1 otherwise)

                'extra' -- extra parameters that the link can store

        """
        Persistent.__init__( self )
        self.id = id

        self.source_uid = sourceObject.getUid()
        self.dest_uid = destinationObject.getUid()

        # types are (depending, reference)
        self.relation_type = relation_type
        self.dest_removed = None

        # extra dictionary handles additional link parameters
        # XXX: ensure that extra values are strings
        if type(extra) is DictType:
            self.extra = extra

        # directions are (direct, reverse)
        self.relation_direction = relation_direction
        self._updateMetadata( sourceObject, destinationObject )

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not Persistent._initstate( self, mode ):
            return 0

        if getattr( self, 'source', None ) is None:
            self.source = {}

        if getattr( self, 'destination', None ) is None:
            self.destination = {}

        return 1

    def getId( self ):
        """
            Returns id of the link
        """
        return self.id

    def _updateMetadata( self, src=None, dst=None ):
        """
            Remembers objects properties according Config.DocumentLinkProperties.

            These properties could be showed to user if the documents will
            be removed or inaccessible due security restrictions.

            Arguments:

                'src' -- source object

                'dst' -- destination object
        """
        for ob, data in [ (src, self.source), (dst, self.destination) ]:
            if ob is None:
                continue
            data.clear()

            for attr in DocumentLinkProperties:
                if hasattr( aq_base(ob), attr ):
                    value = getattr( ob, attr, '' )
                    if callable(value):
                        value = value()
                else:
                    value = ''
                data[ attr ] = value

            self._p_changed = 1

    def Extra( self, name=None ):
        """
            Catalog index routine.

            If no 'name' specified, converts extra params dictionary
            to the list like ['keyA:valueA', 'keyB:valueB', ...]

            Arguments:

                'name' -- If specified, only property with this name will
                    be returned (or None if no such property).

            Result:

                List of strings or string.
        """
        extra = getattr( self, 'extra', {} )
        if name:
            return extra.get( name )

        return [ '%s:%s' % ( key, str(value) ) for key, value in extra.items() ]

    security.declareProtected( CMFCorePermissions.ModifyPortalContent, 'markRemovedDest' )
    def markRemovedDest( self ):
        """
            Tell the link that destination object was removed
        """
        #self.dest_path = None
        self.dest_removed = 1
        self.dest_uid = None

    def isDestinationRemoved( self ):
        """
            Returns true if the destination object is removed.

            Result:

                Boolean.
        """
        return self.dest_removed

    def getSourceUid( self ):
        """
            Returns the link's source object uid.

            Result:

                String.
        """
        return self.source_uid

    def getDestinationUid( self ):
        """
            Returns the link's destination object uid.

            Result:

                String.
        """
        return self.dest_uid

    def getSourceMetadata( self, name ):
        """
            Returns a link's source object metadata.

            Arguments:

                'name' -- attribute name to get
        """
        return self.source.get(name)

    def getDestinationMetadata( self, name ):
        """
            Returns a link's destination object metadata.

            Arguments:

                'name' -- attribute name to get

        """
        return self.destination.get(name)

    def getSourceObject( self, version=0 ):
        """
            Returns the source link object.

            Result:

                Object or None.
        """
        uid = self.getSourceUid()
        object = uid and getObjectByUid(self, uid)
        source_ver_id = self.Extra('source_ver_id')

        if version and object and object.implements('isVersionable') and source_ver_id:
            object = object.getVersion( source_ver_id )

        return object

    def getDestinationObject( self, version=0 ):
        """
            Returns the object that link points to.

            Result:

                Object or None.
        """
        uid = self.getDestinationUid()
        object = uid and getObjectByUid(self, uid)
        destination_ver_id = self.Extra('destination_ver_id')

        if version and object and object.implements('isVersionable') and destination_ver_id:
            object = object.getVersion( destination_ver_id )

        return object

    def getRelationType( self ):
        """
            Returns link relation type.
        """
        return self.relation_type

InitializeClass( Link )

class DocumentLinkTool( CatalogTool, ObjectManager ):
    """
        Portal document link tool is container for links objects.
        Also provides possibility to catalog links.
    """
    _class_version = 1.0

    id = 'portal_links'
    meta_type = 'ExpressSuite DocumentLink Tool'

    security = ClassSecurityInfo()

    relations = ( \
        ('The document depends on current', 'Current depends on the document'),
        ('The help document', 'The help document') \
    )

    def _initstate( self, mode ):
        """
            Initialize attributes
        """
        if not Persistent._initstate( self, mode ):
            return 0

        return 1

    def _containment_onAdd( self, item, container ):
        if not self._catalog._length():
            self.updateCatalog()

    def updateCatalog( self ):
        for x in self.objectValues():
            self.reindexObject( x )
        logger.info("updateCatalog, catalog reindexed, lenght: %s" % len(self.objectIds()))

    security.declarePublic('listRelations')
    def listRelations( self ):
        """
            Converts 2D tuple (self.relations) to single tuple to use in dtml.

            Result:

                Tuple.
        """
        rels = []
        rels.append(self.relations[0][0])
        rels.append(self.relations[0][1])
        rels.append(self.relations[1][0])
        #for typ in 0,1:
        #       for direction in 0,1:
        #               rels.append(self.relations[typ][direction])
        return tuple(rels)

    def enumerateIndexes( self ):
        """
            Returns a list of ( index_name, type ) pairs for the initial index set.
            Overrides CatalogTool's enumerateIndexes().
        """
        return (  ('id', 'FieldIndex')
                , ('meta_type', 'FieldIndex')
                , ('Creator', 'FieldIndex')
                , ('SearchableText', 'TextIndex')
                , ('Date', 'FieldIndex')
                , ('Type', 'FieldIndex')
                , ('created', 'FieldIndex')
                , ('modified', 'FieldIndex')
                , ('source_uid', 'FieldIndex')
                , ('dest_uid', 'FieldIndex')
                , ('relation_type', 'FieldIndex')
                , ('relation_direction', 'FieldIndex')
                , ('dest_removed', 'FieldIndex')
                , ('Extra', 'KeywordIndex')
               )

    def enumerateColumns( self ):
        """
            Returns a sequence of schema names to be cached.

            Overrides CatalogTool's enumerateColumns().
        """
        return (  'id'
                , 'meta_type'
                , 'source_uid'
                , 'dest_uid'
                , 'relation_type'
                , 'relation_direction'
                , 'dest_removed'
                , 'Type'
                , 'Creator'
                , 'Date'
                , 'created'
                , 'modified'
                , 'CreationDate'
                , 'ModificationDate'
            )

    security.declarePublic('getProperRelation')
    def getProperRelation( self, rel_type, rel_direction, source_is_current=None, context=None ):
        """
            Returns string that represents the proper relation (depending on given parameters).

            Arguments:

                'rel_type' -- relation type of the link

                'rel_direction' -- relation direction of the link

                'source_is_current' -- Expects to be 0 or 1: 1 means that the current
                    is source document, 0 means that the current is destination document.

                'context' -- given context, if not None and relation type is 'The help document',
                    we return depending category title.

            Result:

                String.
        """
        if source_is_current:
            # current is source
            x = self.relations[rel_type][rel_direction]
        else:
            x = self.relations[rel_type][1 - rel_direction]
        if context is not None and x == 'The help document':
            metadata = getToolByName( self, 'portal_metadata', None )
            category = context.Category()
            return metadata is not None and category and metadata.getCategoryTitle(category) or x
        return x

    #security.declareProtected( CMFCorePermissions.ManageProperties, 'createLink' )
    security.declareProtected(CMFCorePermissions.View, 'createLink')
    def createLink( self, source_uid=None, destination_uid=None, relation=None, REQUEST=None, **kw ):
        """
            Creates link object using given data.

            Wrapper for _createLink method. Makes all security and other check.
            Converts relation into two parameters - relation_type and relation_direction.
            Then calls _createLink(). Returns id of the created link.

            Arguments:

                'source_uid' -- Uid of the 'source' object (from which the link being created).

                'destination_uid' -- Uid of the 'destination' object (to which the link being created).

                'relation' -- Index for selected relation based upon listRelations.

                'REQUEST' -- REQUEST object.

                '**kw' -- extra parameters to store

            Result:

                String.
        """
        source_uid = source_uid or REQUEST and REQUEST.get('source_uid')
        destination_uid = destination_uid or REQUEST and REQUEST.get('destination_uid')

        # Note: relation value can be '0', None value forces REQUEST to be used.
        relation = relation or relation is None and REQUEST and REQUEST.get('relation')
        extra = kw
        try:
            relation = int(relation)
        except TypeError:
            raise ValueError, 'Invalid relation'

        if not ( source_uid and destination_uid and relation is not None ):
            raise ValueError, 'Too few data'

        # 0..4 -> (0..1, 0..1)
        #we have relation (0..4). Want to have rel. type and direction.
        relation_type = relation_direction = None
        try:
            relation_type = relation / 2
            relation_direction = relation % 2 #- relation_type*2
        except:
            raise ValueError, 'Invalid relation'

        if source_uid == destination_uid:
            error_msg = 'Unable to link document to itself'
            if REQUEST:
                return REQUEST.RESPONSE.redirect( addQueryString(REQUEST['HTTP_REFERER'], \
                       portal_status_message=error_msg) )
            else:
                raise ValueError, error_msg

        # XXX add 'extra' support
        if self.searchLinks( source_uid=source_uid, dest_uid=destination_uid, Extra=extra ):
            error_msg = 'Link exists'
            if REQUEST is not None:
                REQUEST.RESPONSE.redirect( addQueryString(REQUEST['HTTP_REFERER'], \
                       portal_status_message=error_msg) )
            else:
                raise ValueError, error_msg
            return

        catalog = getToolByName( self, 'portal_catalog', None )
        if catalog is None:
            raise KeyError, 'Unable to find the portal_catalog tool'

        sObj = None
        dObj = None

        res = catalog.searchResults( nd_uid=source_uid )
        sObj = res and res[0].getObject() or kw.get('source') or None
        res = catalog.searchResults( nd_uid=destination_uid )
        dObj = res and res[0].getObject()

        link_id = None
        if sObj is not None and dObj is not None:
            #check permissions first
            # XXX have to check perms something like that:
            #     if hasattr(sObj, 'validateLink') and \
            #         sObj.validateLink(dObj, relation_type, relation_direction, extra):
            can_create_link = _checkPermission( CMFCorePermissions.View, sObj )
            if can_create_link:
                link_id = self._createLink( sObj, dObj, relation_type, relation_direction, extra)
            else:
                raise Unauthorized, 'You are not allowed to create link between these documents'
                #return REQUEST.RESPONSE.redirect( REQUEST['HTTP_REFERER']+ \
                #    'You are not allowed to create link between these documents')
        elif sObj is None:
            raise KeyError, 'Link source does not exist or not available'
        else:
            raise KeyError, 'Link destination does not exist or not available'

        if REQUEST is not None:
             REQUEST.RESPONSE.redirect( addQueryString( REQUEST['HTTP_REFERER'], \
                  portal_status_message='Link was successfully created.') )

        return link_id

    def _createLink( self, sourceObject, destinationObject, relation_type, relation_direction, extra=None ):
        """
            Creates link between source and destination objects.

            Puts created link object in self (as object manager) and catalogs it.
            Returns id of the created link.

            Arguments:

                'sourceObject' -- The 'sourse' object (from which the link being created).

                'destinationObject' -- The 'destination' object (to which the link being created).

                'relation_type' -- relation type

                'relation_direction' -- relation direction

                'extra' -- extra parameters to store.

            Result:

                String.

        """
        if sourceObject and hasattr( sourceObject, 'failIfLocked' ):
            sourceObject.failIfLocked()

        id = 'link_' + str( int( random() * 1000000000) )
        while hasattr(self, id):
            id = 'link_' + str( int( random() * 1000000000) )

        link = Link( id, sourceObject, destinationObject, relation_type, relation_direction, extra )
        self._setObject( id, link )
        link = self._getOb( id )

        #link.manage_permission( CMFCorePermissions.View, ( Roles.Member, Roles.Visitor ), 1 )
        self.indexObject( link )
        return id

    def _removeLink( self, link_id, source=None, container=None ):
        """
            Removes link from catalog and storage.

            Checks 'delete' permissions on the source object and then removes
            link with id equal to 'link_id' from catalog and storage.

            Arguments:

                'link_id' -- Id of the link to be removed.

                'source' -- Optional parameter, if omitted, link.getSourceObject() will be called to get it.

                'container' -- Object which is contained of the given destination (such as, reports).
                               We should delete it too.
        """
        link = getattr( self, link_id, None)
        if link is None:
            return
        ob = source or link.getSourceObject()
        if ob is None:
            return

        if hasattr( ob, 'failIfLocked' ):
            ob.failIfLocked()

        can_remove_link = _checkPermission( CMFCorePermissions.View, ob )

        if not ( can_remove_link or getattr( self, '_v_force_links_remove', 0 ) ):
            raise Unauthorized, 'You are not allowed to remove link between these documents'

        if container is not None:
            id = link.getDestinationObject().getId()
            try:
                if id in container.objectIds():
                    container._delObject( id )
            except:
                logger.error('_removeLink Cannot delete linked object: %s\n>container: %s' % ( id, `container` ))

        self.unindexObject( link )
        self._delObject( link_id )

    #security.declareProtected( CMFCorePermissions.ManageProperties, 'removeLinks' )
    security.declareProtected(CMFCorePermissions.View, 'removeLinks')
    def removeLinks( self, ids=None, REQUEST=None, **kw ):
        """
            Removes posted in REQUEST links.

            Calls _removeLink() for each id.

            Arguments:

                'ids' -- List of links identifiers to be removed.

                'REQUEST' -- REQUEST object.
        """
        links_to_remove = ids or REQUEST.get('remove_links', [])
        container = None
        uid = get_param('this_uid', REQUEST, kw, None)
        if uid:
            container = getObjectByUid(self, uid)

        for link_id in links_to_remove:
            self._removeLink( link_id, container=container )

        if REQUEST is not None:
            REQUEST.RESPONSE.redirect( addQueryString(REQUEST['HTTP_REFERER'], \
                portal_status_message='Links were successfully removed.') )

    security.declareProtected(CMFCorePermissions.View, 'removeBoundLinks')
    def removeBoundLinks( self, object ):
        """
            Deletes all links bound with the object.

            Deletes all links bound with given object.
            For documents that are source objects all links will be removed,
            for documents that are destination objects for links there will be marked
            (in links) that destination removed.
            Also checks permissions to delete objects.

            Arguments:

                'object' -- Object for which it is needed to remove bound links.
        """
        if object is not None and _checkPermission( ZopePermissions.delete_objects, object ):
           res1 = self.searchResults( source_uid=object.getUid() )
           for link_brain in res1:
                self._removeLink( link_id=link_brain.getObject().getId(), source=object )
               #res1  -  remove
           res2 = self.searchResults( dest_uid=object.getUid() )
           for link_brain in res2:
              link = link_brain.getObject()
              self._markRemovedDest( link.getId() )
            #res2  -  change 'removed' state
        else:
           raise Unauthorized, 'You are not allowed to remove link between these documents'

    def _markRemovedDest( self, link_id ):
        """
            Tells the link with given id that destination object was removed.

            Arguments:

                'link_id' -- link object identifier
        """
        self[link_id].markRemovedDest()
        self.reindexObject( self[link_id] )

    def _exportLinks( self, uid ):
        """
            Searches all bound with the document with given uid links and exports them.
            Returns dictionary with format { link_id: remote data, ...}.

            Arguments:

                'uid' -- uid of the document.

            Result:

                Dictionary.
        """
        if type(uid) is not StringType:
            uid = uid.getUid()

        results = self.searchResults( source_uid=uid ) + self.searchResults( dest_uid=uid )
        if not results:
            return None

        data = {}
        for res in results:
            data[ res['id'] ] = res.getObject()._remote_export()

        return data

    def _importLinks( self, file ):
        """
            Imports data from file
        """
        links = {}
        for id, data in file.items():
            links[ id ] = self._p_jar.importFile( data )

        uids = map( lambda ln: ln.source_uid, links.values() ) + map( lambda ln: ln.dest_uid, links.values() )

        catalog = getToolByName( self, 'portal_catalog', None )
        results = catalog.unrestrictedSearch( nd_uid=uids )

        found = {}
        for res in results:
            found[ res['nd_uid'] ] = res.getObject()

        for id, link in links.items():
            src = found.get( link.source_uid )
            dst = found.get( link.dest_uid   )

            old = self._getOb( id, None )
            if old is not None:
                old._updateMetadata( src, dst )
                self.reindexObject( old )
                continue

            if src is None or ( dst is None and not link.dest_removed ):
                continue

            self._setObject( id, link )
            link = self._getOb( id )

            link._updateMetadata( src, dst )
            self.reindexObject( link )

    security.declarePublic( 'listClipboardObjects' )
    def listClipboardObjects( self, item=None, REQUEST=None, permission=CMFCorePermissions.ModifyPortalContent ):
        """
            Returns a list of objects in the clipboard for which current user can create links
            from or to the *item*.

            Arguments:

                'item' -- Object from or to which user can create links.

                'REQUEST' -- REQUEST object.

            Result:

                List of objects.
        """
        if item is None:
            uid = None
            linked = []
        else:
            uid = item.getUid()
            linked = map( lambda ob: ob['dest_uid'], self.searchResults( source_uid=uid ) ) + \
                     map( lambda ob: ob['source_uid'], self.searchResults( dest_uid=uid ) )

        oblist = listClipboardObjects( self, permission=permission, REQUEST=REQUEST )
        result = []

        for ob in oblist:
            if ob.implements('isDocument'):
                other = ob.getUid()
                if other and other != uid and other not in linked:
                    result.append( ob )

        return result

    security.declareProtected( CMFCorePermissions.View, 'searchLinks' )
    def searchLinks( self, REQUEST=None, check_permission=None, **kw ):
        """
            Calls ZCatalog.searchResults with extra arguments that limit the results to what
            the user is allowed to see.

            Arguments:

                'REQUEST' -- REQUEST object.

                '**kw' -- Additional parameters. If there is 'Extra' key in the kw, data from dictionary
                          kw['Extra'] will be added to query.

            Result:

                List of results.
        """
        extra = []

        # Additional link parameters can be passed in a Extra dict.
        if kw.has_key('Extra') and type(kw['Extra']) == DictType:
            # we've got a dict and need convert it to a string
            extra_dict = kw['Extra']
            extra = [ '%s:%s' % ( key, extra_dict[key] ) for key in extra_dict.keys() ]
        else:
            indexes = map( lambda x: x[0], self.enumerateIndexes() )
            for key in kw.keys():
                if key not in indexes:
                    # Pass query to the 'Extra' index
                    extra.append( '%s:%s' % ( key, kw[key] ) )
                    del kw[key]

        results = apply(CatalogTool.unrestrictedSearch, (self, REQUEST), kw)

        if extra and results:
            # XXX This is a nasty hack to overcome a Zope Collector Bug #889.
            # Should be replaced with:
            #     kw['Extra'] = { 'query': extra, 'operator': 'and' }
            for key in extra:
                kw['Extra'] = key
                sub = apply(CatalogTool.unrestrictedSearch, (self, REQUEST), kw)
                # 'intersection' substitute
                all_rids = map(lambda x: x.getRID(), results)
                results = filter(lambda x, all_rids=all_rids: x.getRID() in all_rids, sub)

        res = []
        for x in results:
            ob = x.getObject()
            if ob is None: continue
            for key in ('source_uid', 'dest_uid'):
                if not kw.has_key(key):
                    continue
                if key == 'source_uid':
                    obj = ob.getDestinationObject()
                else:
                    obj = ob.getSourceObject()
                if obj is None:
                    continue
                if check_permission and not _checkPermission( CMFCorePermissions.View, obj ):
                    continue
                res.append( x )
                break

        return res

    def getMatchedLinks( self, links, **kw ):
        """
            Additional function for searchLinks
        """
        res = []

        for x in links:
            link = x.getObject()
            if link is None: continue
            if not hasattr( link, 'extra' ): continue
            IsBreak = 0
            for key in kw.keys():
                if link.extra.get(key, None ) != kw[key]:
                    IsBreak = 1
                    break
            if IsBreak: continue
            res.append( x )

        return res

    security.declareProtected( CMFCorePermissions.View, 'getObjectLinks' )
    def getObjectLinks( self, context, from_to=None, relation_type=None, relation_direction=None, return_objects=None ):
        """
            Returns list of object links.

            Arguments:

                'context' -- object to investigate

                'from_to' -- direction 'from/to'

                'relation_type' -- 

                'relation_direction' -- 
        """
        if context is None or not hasattr(context, 'getUid'):
            return []

        uid = context.getUid()
        version_id = context.implements('isDocument') and context.getCurrentVersionId()

        links = []

        if not from_to or from_to in ['from']:
            links.extend( [ ('from', ob) for ob in self.searchLinks( source_uid=uid, source_ver_id=version_id ) ] )
        if not from_to or from_to in ['to']:
            links.extend( [ ('to', ob) for ob in self.searchLinks( dest_uid=uid, source_ver_id=version_id ) ] )

        res = []

        if relation_type is None and relation_direction is None and not return_objects:
            if links:
                return [ link for x, link in links ]
            else:
                return []

        for x, link in links:
            IsOk = 1
            if relation_type is not None:
                IsOk = link.relation_type == relation_type and 1 or 0
            if relation_direction is not None:
                IsOk = link.relation_direction == relation_direction and IsOk or 0
            if IsOk:
                if not return_objects:
                    res.append( link )
                else:
                    ob = x == 'from' and \
                        link.getObject().getDestinationObject() or \
                        link.getObject().getSourceObject()
                    if ob is not None:
                        res.append( ob )

        return res

    security.declarePublic( 'locate' )
    def locate( self, uid=None, REQUEST=None, **kw ):
        """
            Gets resource by uid and kw parameters.

            Arguments:

                'uid' -- uid of object.
        """
        not_found = 'Unfortunatly, requested item was not found.'
        if REQUEST is None:
            return not_found

        membership = getToolByName( self, 'portal_membership', None )
        catalog = getToolByName( self, 'portal_catalog', None )
        if None in ( membership, catalog, ):
            return
        if membership.protection( REQUEST=REQUEST ) != 1:
            return

        if uid:
            params = '?expand=1&link=view'
            res = catalog.unrestrictedSearch( check_permission=0, nd_uid=uid )
            if res:
                ob = res[0].getObject() #_unrestrictedGetObject()
                if ob is not None:
                    url = ob.absolute_url( canonical=1 ) + params
                    return REQUEST.RESPONSE.redirect( url )
                else:
                    uname = _getAuthenticatedUser(self).getUserName()
                    logger.error('locate cannot get object (permissions denied), uid: %s, res: %s, member: %s' % ( uid, len(res), uname ))
            else:
                services = getToolByName( self, 'portal_services', None )
                IsError, res = services.locate( uid )
                res = filter(None, res)
                if res:
                    url = res[0] + params
                    return REQUEST.RESPONSE.redirect( url )
                else:
                    uname = _getAuthenticatedUser(self).getUserName()
                    logger.error('locate not found, uid: %s, member: %s' % ( uid, uname ))

            #archive = getClientStorageType( self )
            #if not archive:
            #    urltool = getToolByName( self, 'portal_url', None )
            #    url = urltool( canonical=True ) + '/archive_search?uid=%s&expand=1' % uid
            #    return REQUEST.RESPONSE.redirect( url )

        return not_found

InitializeClass( DocumentLinkTool )
