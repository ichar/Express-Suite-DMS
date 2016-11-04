## Script (Python) "category_edit"
##bind container=container
##bind context=context
##bind namespace=
##bind script=script
##bind subpath=traverse_subpath
##parameters=
##title=
##
from Products.ExpressSuiteTools.SecureImports import parseDate, parseTime

REQUEST = context.REQUEST
r = REQUEST.get

if REQUEST.has_key('add_template'):
    if context.addTemplate(REQUEST.get('template_uid')):
        message = 'New template added'
    else:
        message = 'New template was not added'
    REQUEST['RESPONSE'].redirect( context.absolute_url(message=message) )

context.setTitle(REQUEST['title'])

lock_timeout = parseTime('lock_timeout', REQUEST)
context.setLockTimeout(lock_timeout)

registry_uid = REQUEST.get('registry_uid',None)
context.setDefaultRegistry( registry_uid )

RN = REQUEST.get('RN')
context.setRN( RN )

RD = REQUEST.get('RD')
context.setRD( RD )

postfix = REQUEST.get('postfix', None)
context.setPostfix( postfix )

message = 'Changes was saved'

if REQUEST.has_key('template_uid_selected'):
    message = ''
    if REQUEST.has_key('remove_template'): 
        if context.deleteTemplates(REQUEST.get('template_uid_selected')):
            message = 'Template removed'
    elif REQUEST.has_key('save_changes'):
        selected_uids = REQUEST.get('template_uid_selected')
        template_edit_fields_only = []
        template_use_translate = []
        template_use_facsimile = []
        wysiwyg_restricted = []

        for uid in selected_uids:
            template_edit_fields_only.append( r('template_edit_fields_only_%s' % uid) )
            template_use_translate.append( r('template_use_translate_%s' % uid) )
            template_use_facsimile.append( r('template_use_facsimile_%s' % uid) )
            wysiwyg_restricted.append( r('wysiwyg_restricted_%s' % uid) )
        
        if context.setTemplateMode( selected_uids, template_edit_fields_only, template_use_translate,  template_use_facsimile, wysiwyg_restricted ):
            message = 'Templates changes saved'

        context.setDefaultTemplate( r('default_template') )

if REQUEST.has_key('save_changes'):
    context.setFreeCookedBodyMode( REQUEST.get('forbid_free_cookedbody', '') )
    context.setReplyToAction( REQUEST.get('reply_to_action', None) )
    context.setLockAttachments( REQUEST.get('lock_attachments', None) )
    context.setImplementLanguage( REQUEST.get('implement_language', None) )

if not message:
    message = "Changes was not saved"

REQUEST['RESPONSE'].redirect( context.absolute_url(message=message) )
