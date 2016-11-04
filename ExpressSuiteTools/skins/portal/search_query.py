## Script (Python) "doFormSearch"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=REQUEST=None, query_id=None, query_title=None, profile_id=None, implements=None, text=None, objects=None, filters=None, transitivity=None, fields=None, otype=None, types=None, owners=None, scope=None, location=None, action=None, category=None, state=None, mode=None, standard_trigger, ctrl_attributes_trigger, special_trigger=None, normative_trigger=None, registry_id=None, sorting=None, search_textonly=None, resolutions=None, expand=None
##title=Pre-process form variables, then return catalog query results.
##
from Products.ExpressSuiteTools.SecureImports import parseString, parseDate, parseDateValue, \
     DateTime, SetSessionValue, portal_log #, portal_info

if profile_id:
    query = context.portal_catalog.getQuery( profile=profile_id, copy=1, REQUEST=REQUEST )
else:
    query = context.portal_catalog.getQuery( query_id, REQUEST=REQUEST )

user_storage_type = context.portal_properties.storage_type()
IsArchive = ( user_storage_type == 'archive' and 1 or 0 )
IsCategory = category and same_type(category, [], ()) and category != 'any' and 1 or 0
IsResolution = ( resolutions or REQUEST.get( 'resolutions', 0 ) ) and 1 or 0

query_id = query.getId()

IsSomeItem = 0
for item in ( 'oid', 'title', 'description', 'registry_id', ):
    if REQUEST.has_key( item ) and REQUEST[item]:
        setattr( query, item, str( REQUEST[item] ) )
        IsSomeItem = 1

created_from = parseDate( 'created_from', REQUEST, None )
created_till = parseDate( 'created_till', REQUEST, None )

IsEmptyDate = not ( created_from or created_till ) and 1 or 0
created_search_interval = context.portal_properties.getProperty( 'created_search_interval' ) or 0

IsEmptyQuery = IsEmptyDate and not IsSomeItem and not IsCategory and not IsResolution and \
               not owners and not profile_id and (not otype or otype == 'HTMLDocument') and 1 or 0

if text and ( not profile_id or query.text != text ):
    search_text = text.lower()
    s_keys = ()
    is_restricted = 1

    for key in s_keys:
        if key == ':':
            is_restricted = 0
        if search_text.find(key) > -1:
            if is_restricted:
                setattr( query, 'message', 'This keyword is restricted! Try more exactly. $ %s' % text )
                text = None
            created_till = DateTime()
            created_from = created_till - ( IsArchive and created_search_interval or 30 )
            IsEmptyDate = 0
            break

    query.text = parseString( text )
    if text and REQUEST.has_key( 'search_textonly' ) and REQUEST['search_textonly']:
        setattr( query, 'sorting', 'ABC' )

for item in ['sorting']:
    if REQUEST.has_key( item ):
        setattr( query, item, str( REQUEST[item] ) )

if IsEmptyQuery and not text:
    #if IsArchive:
    #    created_till = DateTime() - created_search_interval
    #else:
    #    created_till = DateTime()
    pass

if not IsEmptyDate:
    if created_till and not created_from:
        if created_search_interval:
            created_from = created_till - created_search_interval
    if created_from and created_till:
        query.creation = ( created_from, created_till and created_till + 0.99999, )
    elif created_from:
        query.creation = ( created_from, None, )
    elif created_till:
        query.creation = ( None, created_till, )

if objects is not None:
    query.objects = filter( None, objects )

if IsResolution:
    query.hasResolution = 1
    query.implements = ['isVersionable']
    query.types = ['HTMLDocument']
    query.state = state or REQUEST.get('state', None)

if implements is not None:
    query.implements = filter( None, implements )
else:
    query.implements = []

if otype is not None:
    #if IsArchive:
    #    query.implements.append('isHTMLDocument')
    if otype == 'Attachments':
        query.implements.append('isAttachment')
    elif otype == 'HTMLDocument':
        query.implements.append('isHTMLDocument')
    elif otype == 'any':
        query.types = ['any']
    else:
        query.types = [otype]
elif types is not None:
    query.types = types

if special_trigger:
    if normative_trigger:
        if transitivity is not None:
            query.transitivity = transitivity

if filters is not None:
    query.filters = filter( None, filters )
    # show another dtml for search over documents for revision
    if 'normative_filter' in query.filters:
        action = 'search_results_ndocument'

if fields is not None:
    query.fields = filter( None, fields )
    if 'fields' not in query.objects:
        query.objects.append( 'fields' )

if IsCategory:
    query.category = category
    if len(category) == 1:
        category_id = category[0]
        attributes = {}
        extract_Factory = { 'int' :int, 'float' : float, 'currency' : float, 'date' : parseDateValue }
        operator = None

        c = context.portal_metadata.getCategoryById(category_id)
        for attr in c.listAttributeDefinitions():
            attr_id = attr.getId()
            attr_value = REQUEST.get(category_id + '_' + attr_id)
            in_child = REQUEST.get(category_id + '_' + attr_id + '_inchild')
            #
            #portal_info('attr id:%s, value:%s, in_child:%s' % (attr_id, attr_value, in_child))
            #
            value = range = None
            condition_value = '%s_%s' % ( category_id, attr_id )

            if not REQUEST.has_key('conditions_' + category_id ) or \
                condition_value not in REQUEST.get( 'conditions_' + category_id ):
                continue

            attr_type = attr.Type()
            if attr_type == 'boolean':
                value = attr_value[0] != 'false' and True or False

            elif attr_type in ('string', 'text'):
                #
                #portal_info('string attr_value:%s' % attr_value)
                #
                attr_value = parseString( attr_value[0].split(':::') )
                value = attr_value + '%'
                if not in_child:
                    value = value.replace('%', '') + '%'
                #
                #portal_info('value:%s' % value)
                #
            elif attr_type in ('lines','items', 'userlist'):
                #
                #portal_info('items attr_value:%s' % attr_value)
                #
                attr_value = attr_value[0].split(':::')
                value = attr_value
                operator = 'OR'
                range = ''
                #
                #portal_info('value:%s' % value)
                #
            elif attr_type in ('int', 'float', 'currency', 'date'):
                attr_value = attr_value[0].split(':::')
                min_max = ('min','max',)
                value = []
                range = ''
                for idx in (0,1):
                    if attr_value[idx]:
                        value.append( extract_Factory[attr_type]( attr_value[idx] ) )
                        if range:
                            range += ':'
                        range += min_max[idx]

            if range:
                attributes[attr_id] = { 'query' : value, 'range' : range }
            elif operator:
                attributes[attr_id] = { 'query' : value, 'operator' : operator }
            else:
                attributes[attr_id] = value

        if attributes:
            if len(attributes.keys()) > 1:
                query.attributes = { 'query' : attributes, 'operator' : 'AND' }
            elif same_type(attributes.values()[0], {}):
                query.attributes = attributes.values()[0]
            else:
                query.attributes = { 'query' : attributes }
        #
        #portal_info('guery attributes:%s, value:%s' % (attributes, query.attributes))
        #

        if state is not None and otype in ( 'HTMLDocument', 'Task Item', 'Image Attachment', 'File Attachment', ):
            if same_type(state, {}):
                if state.has_key(category_id) and state[category_id] != 'any':
                    query.state = state[category_id]
            else:
                query.state = state

if owners is not None:
    query.owners = filter( None, owners )

if scope == 'preserved':
    pass
elif location:
    query.scope = scope or 'recursive'
    query.location = location
elif query.location:
    query.scope = scope or 'global'
else:
    query.scope = 'global'

params = {}
frame = not REQUEST.get('callback_form') and 'inFrame' or None

if expand:
    params['expand'] = 1
    frame = None

if query_title:
    params['query_title'] = query_title

if not REQUEST.get('save') or REQUEST.get('search_attrs'):
    params['query_id'] = query_id
    params['batch_length'] = REQUEST.get('batch_length')
    params['callback_form'] = REQUEST.get('callback_form')
    params['callback_uid_field'] = REQUEST.get('callback_uid_field')
    params['callback_uid_title'] = REQUEST.get('callback_uid_title')
    params['callback_function'] = REQUEST.get('callback_function')
    params['uid_field'] = REQUEST.get('uid_field')
    params['title_field'] = REQUEST.get('title_field')
    params['getPath'] = REQUEST.get('getPath')
    params['registry_id'] = REQUEST.get('registry_id')

    if REQUEST.has_key('adv_search'):
        params['adv_search'] = 1

    query_location = context.restrictedTraverse( query.location )
    return query_location.redirect( action=(action or 'search_results'), frame=frame, params=params )

elif profile_id:
    profile = context.portal_catalog.getObjectByUid( profile_id )
    profile.setQuery( query )
    return profile.redirect( action='view', frame=frame, message="Search query saved." )

else:
    params['type_name'] = 'Search Profile'
    params['type_args'] = [ query_id ]
    folder = context.portal_membership.getPersonalFolder( 'searches', create=1 )
    SetSessionValue( context, 'search_%s' % query_id, query, REQUEST )
    return folder.redirect( action='invoke_factory_form', frame=frame, params=params )
