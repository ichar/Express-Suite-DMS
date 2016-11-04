## Script (Python) "report_options"
##parameters=title, description=None, allowed_groups=(), allowed_members=()
##title=Add a report item
REQUEST = context.REQUEST

context.setAllowedUsers(allowed_members, allowed_groups)

context.editMetadata( title=title
                    , description=description
                    )

context.reindexObject()

if REQUEST is not None:
     message = ""
     r = REQUEST.get

     if r('add_field'):
        fname = r('fname')
        ftitle = r('ftitle')
        ftype = r('ftype')

        if fname:
            context.addColumn( id = fname
                          , title = ftitle
                          , typ = ftype
                          )

            message = "Field added"

        REQUEST[ 'RESPONSE' ].redirect(context.absolute_url() + '/report_options_form'
                                      + '?portal_status_message=' + message)
     elif r('del_fields'):
        ids=r('selected_fields')
        for id in ids:
            context.delColumn(id)

        if ids:
            message = "Field removed"

        REQUEST[ 'RESPONSE' ].redirect(context.absolute_url() + '/report_options_form'
                                      + '?portal_status_message=' + message)
     else:
        if not context.listColumns():
            message = "You have to specify at least one report field"
            REQUEST[ 'RESPONSE' ].redirect(context.absolute_url() + '/report_options_form'
                                          + '?portal_status_message=' + message)
        else:
            message = "Changes saved"
            REQUEST[ 'RESPONSE' ].redirect(context.absolute_url()
                                          + '?portal_status_message=' + message)


