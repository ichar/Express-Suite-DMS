## Script (Python) "category_metadata"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=
##title=Change allowed subjects for the given content type
##
from Products.ExpressSuiteTools.SecureImports import parseDate, portal_log

REQUEST = context.REQUEST
r = REQUEST.get

message = ''

def getLinkDefault( id, category, REQUEST ):
    default = REQUEST.get(id)
    if default == '2':
        default = '2:%s' % REQUEST.get(category, '')
    return default

if REQUEST.has_key('addField'):
    #Add new category attribute
    fType, fName = r('fType'), r('fName')

    if fType == 'date':
        value = parseDate('value', REQUEST, default=None)
    elif fType == 'link':
        value = r('value_link', {}).get('uid') or None
    elif fType == 'table':
        value = r('value_table', {}).get('count')
    else:
        value = r('value_%s' % fType, '')

    get_default = 0
    if r('current_%s' % fType):
        if fType == 'string':
            get_default = int(r('default_value_string'))
        elif fName.lower().endswith('department'):
            get_default = 1
        elif fType != 'lines':
            get_default = 1

    if fType == 'link':
        get_default = getLinkDefault( 'default_link', 'link_default_category', REQUEST )

    options = r('options_%s' % fType) or None

    context.addAttributeDefinition( fName,
                                    fType,
                                    r('title'),
                                    value,
                                    mandatory=r('mandatory'),
                                    read_only=r('read_only'),
                                    hidden=r('hidden'),
                                    sortkey=r('fSortkey'),
                                    width=r('fWidth'),
                                    editable_in_template=r('editable_in_template'),
                                    get_default=get_default, 
                                    options=options
                                  )

if REQUEST.has_key('deleteField'):
    #Delete attributes
    if REQUEST.has_key('fields'):
        context.deleteAttributeDefinitions(r('fields'))
    else:
        message = 'Select one or more fields first'
        return REQUEST['RESPONSE'].redirect( context.absolute_url( action='category_metadata_form', message=message ))

if REQUEST.has_key('saveValues'):
    #Saving properties and default values for all metadata fields
    for attr in context.listAttributeDefinitions():
        if attr.isInCategory(context):
            id = attr.getId()
            typ = attr.Type()
            
            if typ == 'date':
                value = parseDate('default_%s' % id, REQUEST, default=None )
                if value:
                    value = str(value)
            elif typ in ['lines','items']:
                value = list(r('default_%s' % id))
            elif typ == 'link':
                value = r('default_%s' % id, {}).get('uid') or None
            elif typ == 'string':
                value = r('default_%s' % id)
                if not value:
                    value = ''
            elif typ in ['int', 'float']:
                value = r('default_%s' % id)
                if not value:
                    value = 0
            elif typ == 'table':
                value = r('default_%s' % id, {}).get('count')
            else:
                value = r('default_%s' % id)

            attr.setDefaultValue( value )
            attr.setTitle( r('title_%s' % id) )
            attr.setMandatory( r('mandatory_%s' % id) )
            attr.setReadOnly( r('readonly_%s' % id) )
            attr.setEditable( r('editable_in_template_%s' % id) )
            attr.setHidden( r('hidden_%s' % id) )
            attr.setSortkey( r('sortkey_%s' % id) )
            attr.setWidth( r('width_%s' % id) )
            attr.setOptions( r('options_%s' % id) )

            if typ in ['date', 'userlist']:
                attr.setComputedDefault( r('current_%s' % id) and 1 or 0 )
            elif typ == 'lines':
                get_default = REQUEST.get('current_%s' % id)
                attr.setComputedDefault( get_default )
            elif typ == 'link':
                get_default = getLinkDefault( 'current_%s' % id, '%s_default_category' % id, REQUEST )
                #portal_log( context, 'category_metadata', 'saveValues', 'default_lines', ( default, current_name), force=1 )
                attr.setComputedDefault( get_default )

    message = 'Changes saved'

if REQUEST.has_key('saveField'):
    #Saving changes for a field
    id = r('fName')
    typ = r('fType')
    title = r('title')
    sortkey = r('fSortkey')
    width = r('fWidth')

    attr = context.getAttributeDefinition( id )

    #Get default computed value options, specially for string, lines or another
    if typ == 'string':
        get_default = int(r('default_value_string'))
    elif typ in ['date','userlist']:
        get_default = r('default_%s' % typ)
    elif typ == 'lines':
        get_default = REQUEST.get('default_lines', [])
    elif typ == 'link':
        get_default = getLinkDefault( 'default_link', 'link_default_category', REQUEST )
    else:
        get_default = None

    message = ''

    #Get default value
    if typ == 'date':
        value = parseDate('value', REQUEST, default=None)
    elif typ in ['lines','items']:
        value = list(r('value_%s' % typ))
    elif typ == 'link':
        value = r('value_link', {}).get('uid') or None
    elif typ == 'table':
        value = r('value_table', {}).get('count')
    else:
        value = r('value_%s' % typ, '')

    #Get field options
    options = r('options_%s' % typ) or None

    #Update attribute
    if attr is not None and typ == attr.Type():
        attr.setDefaultValue( value )
        attr.setTitle( title )
        attr.setMandatory( r('mandatory') )
        attr.setReadOnly( r('read_only') )
        attr.setEditable( r('editable_in_template') )
        attr.setHidden( r('hidden') )
        attr.setSortkey( sortkey )
        attr.setWidth( width )
        attr.setComputedDefault( get_default )
        attr.setOptions( options )

        if r('change_data'):
            value_from = r('change_data_from')
            value_to = r('change_data_to')
            reindex = r('change_reindex')

            IsError = context.changeAttributeValue( id, value_from, value_to, reindex, REQUEST )

            if IsError == 0:
                message = 'Field values changed succesfully'
            elif IsError < 3:
                message = 'Field type conversion error'
            else:
                message = 'Field was specified incorrectly'

    #Delete previous and add new attribute definition
    else:
        if REQUEST.has_key('fields'):
            id_from = r('fields')
            id_from = id_from[0]
        else:
            id_from = ''

        if id_from is None or id_from == '':
            IsGo = 0
        elif id_from == id:
            context.deleteAttributeDefinitions( (id_from,) )
            IsGo = 0
        else:
            IsGo = 1

        context.addAttributeDefinition( 
               id,
               typ,
               title,
               value,
               mandatory=r('mandatory'),
               read_only=r('read_only'),
               hidden=r('hidden'),
               sortkey=r('fSortkey'),
               width=r('fWidth'),
               get_default=get_default,
               options=options
        )

        if IsGo:
            IsError = context.copyAttributeValue( id_from=id_from, id_to=id )
            if not IsError or IsError == 1:
                context.deleteAttributeDefinitions( r('fields') )
                if IsError == 0:
                    message = 'Field transformed succesfully' # +id+':'+typ+':'+title+' from '+id_from+': '+str(IsError)+ ']'
                elif IsError < 3:
                    message = 'Field type conversion error'
                else:
                    message = 'Field was specified incorrectly'

    if REQUEST.has_key('linked_method'):
        context.setAttributeLinkedMethod( id, r('linked_method'), r('linked_attribute') )

    if message is None or message == '':
        message = 'Changes saved'

REQUEST['RESPONSE'].redirect( context.absolute_url(action='category_metadata_form', message=message) )
