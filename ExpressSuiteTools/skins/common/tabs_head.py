## Script (Python) "tabs_head"
##parameters=tabs, sel_tab={'number':-1}, highlight_colors=('#dddeee',), auto_select=None
##title=Renders tabs head widget
##
URL = context.REQUEST.get('URL')

portal_url = context.portal_url()
sel_tab_num = sel_tab.get('number',-1)
sel_tab_color = sel_tab.get('color','#f2f2f2')

ret = '<table cellspacing="0" cellpadding="0" border="0" width="100%" height="100%">\n'\
      '<tr>\n'

for i in range(len(tabs)):
    tab_get = tabs[i].get
    tab_url = tab_get('url')
    tab_icon = tab_get('icon')
    if tab_icon:
        tab_title = tab_get('title','')
    else:
        tab_title = tab_get('title','no title')
    tab_icon_text = tab_get('icon_text')
    ret += '<td valign="bottom">\n'
    if i == sel_tab_num or auto_select and tab_url == URL[-len(tab_url):]:
        ret += '<table cellspacing="0" cellpadding="0" border="0" height="100%%" bgcolor="%s">\n'\
               '<tr height="4">\n'\
               '<td width="4"><img src="%s/uho_click_left_top.gif" width="4" height="4"></td>\n'\
               '<td background="%s/uho_click_center.gif"></td>\n'\
               '<td width="4"><img src="%s/uho_click_right_top.gif" width="4" height="4"></td>\n'\
               '</tr><tr>\n'\
               '<td background="%s/uho_click_left_middle.gif"></td>\n'\
               '<td align="center" nowrap style="padding-left:10px;padding-right:10px;">'\
                % tuple([sel_tab_color] + [portal_url]*4)
        if tab_icon:
            if tab_icon_text:
                ret += tab_icon.tag(align='absmiddle', alt=tab_icon_text)
            else:
                ret += tab_icon.tag(align='absmiddle')
            if tab_title: ret += '&nbsp;'

        ret += '<strong><a class="tabs" href="%s">%s</a></strong></td>\n'\
               '<td background="%s/uho_click_right_middle.gif"></td>\n'\
               '</tr><tr height="3">\n'\
               '<td><img src="%s/uho_click_left_bottom.gif" width="4" height="3"></td>\n'\
               '<td></td>\n'\
               '<td><img src="%s/uho_click_right_bottom.gif" width="4" height="3"></td>\n'\
               '</tr>\n'\
               '</table>\n'\
                % tuple([tab_url,tab_title] + [portal_url]*3)
    else:
        ret += '<table cellspacing="0" cellpadding="0" border="0" height="100%%" bgcolor="%s" %s'\
               'onclick="javascript:location.href=this.getElementsByTagName(\'a\')[0].href;return false;" style="cursor: Pointer;">\n'\
               '<tr height="4">\n'\
               '<td width="4"><img src="%s/uho_left_top.gif" width="4" height="4"></td>\n'\
               '<td background="%s/uho_center_top.gif"></td>\n'\
               '<td width="4"><img src="%s/uho_right_top.gif" width="4" height="4"></td>\n'\
               '</tr><tr>\n'\
               '<td background="%s/uho_left_middle.gif"></td>\n'\
               '<td align="center" nowrap style="padding: 0 10px 0 10px;">'\
                % tuple([highlight_colors[0], \
                         len(highlight_colors) == 2 and 'onmouseover="javascript:this.bgColor=\''+highlight_colors[1]+'\'" ' + \
                                                        'onmouseout ="javascript:this.bgColor=\''+highlight_colors[0]+'\'"' or ''] + \
                        [portal_url]*4)

        if tab_url:
            ret += '<a class="tabs" href="%s">' % (tab_url)

        if tab_icon:
            if tab_icon_text:
                ret += tab_icon.tag(align='absmiddle', alt=tab_icon_text)
            else:
                ret += tab_icon.tag(align='absmiddle')
            if tab_title: ret += '&nbsp;'

        ret += tab_title

        if tab_url:
            ret += '</a>'

        ret += '</td>\n'\
               '<td background="%s/uho_right_middle.gif"></td>\n'\
               '</tr><tr height="3">\n'\
               '<td><img src="%s/uho_left_bottom.gif" width="4" height="3"></td>\n'\
               '<td background="%s/uho_center_bottom.gif"></td>\n'\
               '<td><img src="%s/uho_right_bottom.gif" width="4" height="3"></td>\n'\
               '</tr>\n'\
               '</table>\n'\
                % tuple([portal_url]*4)

    ret += '</td>\n'

ret += '<td width="100%%">\n'\
       '<table cellspacing="0" cellpadding="0" border="0" width="100%%" height="100%%">\n'\
       '<tr><td></td></tr>\n'\
       '<tr height="3"><td background="%s/right_ftd.gif"></td></tr>\n'\
       '</table>\n'\
       '</td></tr>\n'\
       '</table>\n'\
        % (portal_url)

return ret
