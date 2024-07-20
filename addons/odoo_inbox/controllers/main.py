# -*- coding: utf-8 -*-
# Powered by Kanak Infosystems LLP.
# © 2020 Kanak Infosystems LLP. (<https://www.kanakinfosystems.com>).

import base64
import logging
import json
import werkzeug
from datetime import datetime, timedelta
from odoo.addons.portal.controllers.portal import pager
from odoo import http, tools
from odoo.http import request
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.exceptions import AccessError
_logger = logging.getLogger(__name__)


class WebsiteOdooInbox(http.Controller):

    _message_per_page = 20

    def pager(self, url, total, page=1, step=30, scope=5, url_args=None):
        return pager(url, total, page=page, step=step, scope=scope, url_args=url_args)

    def get_message_counter_domain(self, model_object, domain):
        query = model_object._where_calc(domain)
        # model_object._apply_ir_rules(query, 'read')
        from_clause, where_clause, where_clause_params = query.get_sql()
        where_str = where_clause and (" WHERE %s" % where_clause) or ''
        query_str = 'SELECT "%s".id FROM ' % 'mail_message' + from_clause + where_str
        request._cr.execute(query_str, where_clause_params)
        message_ids = request._cr.fetchall()
        message_ids = message_ids and [x[0] for x in message_ids] or []
        return message_ids

    def _render_odoo_message(self, domain=[], link='/mail', page=1, label=None, color='bluecolor', search=None, existing_tag=None, existing_folder=None, partner=None):
        if not label:
            label = 'inbox'
        if label == 'inbox':
            domain += [('folder_id', '=', False)]

        MailMessage = request.env['mail.message'].sudo()
        
        messages = []
        default_inbox_pane_type = 'none'
        user_id = request.env.user
        uid = request.env.uid
        # domain += [('model', '!=', False)]
        counter_domain = []
        # if label == 'sent':
        #     partner_id = request.env.user.partner_id
        if user_id:
            partner_id = partner if partner else request.env.user.partner_id
            default_inbox_pane_type = request.env.user.inbox_default_pane_view_type
            if partner_id:
                if label != 'sent' and label != 'trash':
                    domain += ['|', '|', ('partner_ids', 'in', partner_id.ids), ('notified_partner_ids', 'in', partner_id.ids), ('starred_partner_ids', 'in', partner_id.ids)]

                # In Trash show only own author_id messages only
                if label == 'trash':
                    domain += [('author_id', '=', request.env.user.partner_id.id)]

                counter_domain += ['|', '|', ('partner_ids', 'in', partner_id.ids), ('notified_partner_ids', 'in', partner_id.ids), ('starred_partner_ids', 'in', partner_id.ids)]
        mails = MailMessage.search(domain, offset=(page-1)*self._message_per_page, limit=self._message_per_page, order="date desc")
        for msg in mails:
            record = False
            if msg.model and msg.res_id:
                record = request.env[msg.model].browse(msg.res_id)
            try:
                if record:
                    record.with_user(uid).check_access_rule('read')
            except AccessError:
                continue
            messages.append({'parent_id': msg, 'child_ids': sorted(msg.child_ids, key=lambda r: r.date, reverse=True)})
            
        tag_ids = request.env['message.tag'].sudo().search([('user_id', '=', user_id.id)])
        folder_ids = request.env['message.folder'].sudo().search([('user_id', '=', user_id.id)])
        user_child_partner_ids = request.env.user.child_partner_ids

        inbox_domain = counter_domain + [('msg_unread', '=', False), ('message_label', 'in', ['inbox', 'starred']), ('folder_id', '=', False)]
        inbox_mssg_count = len(self.get_message_counter_domain(MailMessage, inbox_domain))
        starred_domain = counter_domain + [('message_label', '=', 'starred')]
        starred_mssg_count = len(self.get_message_counter_domain(MailMessage, starred_domain))
        snoozed_domain = counter_domain + [('message_label', '=', 'snoozed')]
        snoozed_mssg_count = len(self.get_message_counter_domain(MailMessage, snoozed_domain))
        folder_domain = counter_domain + [('folder_id', '=', existing_folder)]
        folder_mssg_count = len(self.get_message_counter_domain(MailMessage, folder_domain))
        tag_domain = counter_domain + [('tag_ids', 'in', [existing_tag])]
        tag_mssg_count = len(self.get_message_counter_domain(MailMessage, tag_domain))

        counter_fd_msgs = {}
        for fid in folder_ids.ids:
            ffolder_domain = counter_domain + [('msg_unread', '=', False), ('folder_id', '=', fid)]
            ct = len(self.get_message_counter_domain(MailMessage, ffolder_domain))
            counter_fd_msgs.update({str(fid): str(ct)})

        total = 0
        if label == 'inbox':
            tinbox_domain = counter_domain + [('message_label', 'in', ['inbox', 'starred']), ('folder_id', '=', False)]
            total = len(self.get_message_counter_domain(MailMessage, tinbox_domain))
        elif label == 'starred':
            total = starred_mssg_count
        elif label == 'snoozed':
            total = snoozed_mssg_count
        elif existing_folder:
            total = folder_mssg_count
        elif existing_tag:
            total = tag_mssg_count

        pager = self.pager(
            url=link,
            total=total,
            page=page,
            step=self._message_per_page,
        )
        document_models = request.env['ir.model'].sudo().search([('is_mail_thread', '=', True)])
        return request.render('odoo_inbox.inbox', {
            'messages': messages,
            'pager': pager,
            'total': total,
            'starred': label == 'starred' and True or False,
            'done': label == 'done' and True or False,
            'snooze': label == 'snoozed' and True or False,
            'draft': label == 'draft' and True or False,
            'sent': label == 'sent' and True or False,
            'trash': label == 'trash' and True or False,
            'label': label,
            'color': color,
            'search': search,
            'tag_ids': tag_ids,
            'current_partner': partner if partner else request.env.user.partner_id,
            'user_child_partner_ids': user_child_partner_ids,
            'existing_tag': existing_tag,
            'folder_ids': folder_ids,
            'existing_folder': existing_folder,
            'inbox_mssg_count': inbox_mssg_count,
            'starred_mssg_count': starred_mssg_count,
            'snoozed_mssg_count': snoozed_mssg_count,
            'folder_mssg_count': folder_mssg_count,
            'counter_fd_msgs': counter_fd_msgs,
            'document_models': document_models,
            'default_inbox_pane_type': default_inbox_pane_type,
        })

    @http.route(['/mail/message_read'], type='json', auth="user", website=True)
    def odoo_message_read(self, **kw):
        message = request.env['mail.message'].browse(kw.get('message'))
        for m in message:
            
            m.msg_unread = True
        domain = []
        MailMessage = request.env['mail.message'].sudo()
        user_id = request.env.user
        if user_id:
            partner_id = request.env.user.partner_id
            if partner_id:
                domain = ['|', '|', ('partner_ids', 'in', partner_id.ids), ('notified_partner_ids', 'in', partner_id.ids), ('starred_partner_ids', 'in', partner_id.ids)]

        inbox_domain = domain + [('msg_unread', '=', False), ('message_label', 'in', ['inbox', 'starred']), ('folder_id', '=', False)]
        inbox_mssg_count = len(self.get_message_counter_domain(MailMessage, inbox_domain))
        starred_domain = domain + [('msg_unread', '=', False), ('message_label', '=', 'starred')]
        starred_mssg_count = len(self.get_message_counter_domain(MailMessage, starred_domain))
        snoozed_domain = domain + [('msg_unread', '=', False), ('message_label', '=', 'snoozed')]
        snoozed_mssg_count = len(self.get_message_counter_domain(MailMessage, snoozed_domain))
        folder_domain = domain + [('msg_unread', '=', False), ('folder_id', '!=', False)]
        folder_mssg_count = len(self.get_message_counter_domain(MailMessage, folder_domain))

        folder_ids = request.env['message.folder'].sudo().search([('user_id', '=', user_id.id)])
        counter_fd_msgs = {}
        for fid in folder_ids.ids:
            ffolder_domain = domain + [('msg_unread', '=', False), ('folder_id', '=', fid)]
            ct = len(self.get_message_counter_domain(MailMessage, ffolder_domain))
            counter_fd_msgs.update({str(fid): str(ct)})

        uid = request.env.uid
        message_dict = {}
        if message:
            record = False
            if message.model and message.res_id:
                record = request.env[message.model].browse(message.res_id)
            try:
                if record:
                    record.with_user(uid).check_access_rule('read')
            except AccessError:
                pass
            message_dict.update({'parent_id': message, 'child_ids': sorted(message.child_ids, key=lambda r: r.date, reverse=True)})
        message_body = request.env['ir.ui.view']._render_template("odoo_inbox.inbox_message_detail", {
            'mail': message_dict,
        })
        return {'msg_unread': True,
                'inbox_mssg_count': inbox_mssg_count,
                'starred_mssg_count': starred_mssg_count,
                'snoozed_mssg_count': snoozed_mssg_count,
                'folder_mssg_count': folder_mssg_count,
                'counter_fd_msgs': counter_fd_msgs,
                'message_body': message_body}

    @http.route(['/mail/all_mssg_unread'], type='json', auth="user", website=True)
    def odoo_all_message_unread(self, messg_ids, **kw):
        for mssg in messg_ids:
            message = request.env['mail.message'].sudo().browse(int(mssg))
            message.msg_unread = False
        return True

    @http.route(['/mail/all_mssg_read'], type='json', auth="user", website=True)
    def odoo_all_message_read(self, messg_ids, **kw):
        for mssg in messg_ids:
            message = request.env['mail.message'].sudo().browse(int(mssg))
            message.msg_unread = True
        return True

    @http.route(['/mail/inbox',
                 '/mail/inbox/page/<int:page>',
                 '/mail/search_message'
                 ], type='http', auth="user", website=True)
    def odoo_inbox(self, page=1, **kw):
        search = None
        if kw.get('search'):
            domain = ['|', '|', '|',
                      ('subject', 'ilike', kw.get('search')),
                      ('email_from', 'ilike', kw.get('search')),
                      ('body', 'ilike', kw.get('search')),
                      ('tag_ids.name', 'ilike', kw.get('search'))]
            search = kw.get('search')
        else:
            domain = [('message_label', 'in', ['starred', 'inbox'])]
        return self._render_odoo_message(
            domain, '/mail/inbox', page, 'inbox', search=search, color='bluecolor')

    @http.route(['/mail/message_post'], type='http', auth="user", website=True)
    def message_post_send(self, **post):
        subject = post.get('subject')
        body = post.get('body')
        messageObj = request.env['mail.message'].browse(int(post.get('message_id')))
        if messageObj.author_id:
            message_object = False
            if messageObj.model and messageObj.res_id:
                message_object = request.env[messageObj.model].search([('id', '=', int(messageObj.res_id))])
            if not message_object:
                message_object = messageObj.author_id
            partner = messageObj.author_id
            files = request.httprequest.files.getlist('attachments')
            attachment_ids = []
            if files:
                for i in files:
                    if i.filename != '':
                        attachments = {
                                'name': i.filename,
                                'res_name': i.filename,
                                'res_model': 'res.partner',
                                'res_id': partner.id,
                                'datas': base64.encodebytes(i.read()),
                            }
                        attachment = request.env['ir.attachment'].sudo().create(attachments)
                        attachment_ids.append(attachment.id)

            message = message_object.message_post(
                    body=body,
                    subject=subject,
                    email_from='%s <%s>' % (request.env.user.name, request.env.user.email),
                    author_id=request.env.user.partner_id.id,
                    parent_id=messageObj.id,
                    subtype_id=messageObj.subtype_id.id,
                    attachment_ids=attachment_ids,
                    partner_ids=[partner.id],
                    message_type=messageObj.message_type,
                )

            message.write({'msg_unread': False})
        else:
            partner = request.env.user.partner_id
            files = request.httprequest.files.getlist('attachments')
            attachment_ids = []
            if files:
                for i in files:
                    if i.filename != '':
                        attachments = {
                                'name': i.filename,
                                'res_name': i.filename,
                                'res_model': 'res.partner',
                                'res_id': partner.id,
                                'datas': base64.encodebytes(i.read()),
                            }
                        attachment = request.env['ir.attachment'].sudo().create(attachments)
                        attachment_ids.append(attachment.id)
            mailObj = request.env['mail.mail'].sudo().create({
                    'mail_message_id': messageObj.id,
                    'email_to': messageObj.email_from.split('<')[1].split('>')[0],
                    'email_from': '%s <%s>' % (request.env.user.name, request.env.user.email),
                    'reply_to': '%s <%s>' % (request.env.user.name, request.env.user.email),
                    'body_html': post.get('body'),
                })
            mailObj.sudo().send()
            message_object = request.env[messageObj.model].sudo().search([('id', '=', int(messageObj.res_id))])
            message = message_object.sudo().message_post(
                    body=body,
                    subject=subject,
                    email_from='%s <%s>' % (request.env.user.name, request.env.user.email),
                    parent_id=mailObj.mail_message_id.id,
                    subtype_id=mailObj.mail_message_id.subtype_id.id,
                    attachment_ids=attachment_ids,
                    message_type=mailObj.mail_message_id.message_type,
                )
            message.sudo().write({'msg_unread': False})
            mailObj.sudo().unlink()
        return request.redirect('/mail/inbox')

    @http.route(['/sent_mail/mail'], type='http', auth="user", website=True)
    def mail_send(self, **post):
        if post:
            partners = request.httprequest.form.getlist('partners')
            # if partners:
            #     post['partners_list'] = map(int, partners)
            cc_partners = request.httprequest.form.getlist('cc_partners')
            # if cc_partners:
            #     post['cc_partners_list'] = map(int, cc_partners)
            bcc_partners = request.httprequest.form.getlist('bcc_partners')
            # if bcc_partners:
            #     post['bcc_partners_list'] = map(int, bcc_partners)
            subject = post.get('subject')
            body = post.get('body')
            model_name = post.get('document_model') if post.get('document_model') != '0' else False
            res_id = post.get('document_model_record') if post.get('document_model_record') != '0' else False
            message_object = False
            if model_name and res_id:
                message_object = request.env[model_name].search([('id', '=', int(res_id))])
            if not message_object:
                message_object = request.env.user.partner_id
            partner_ids = email_cc_ids = email_bcc_ids = False
            if partners:
                partner_ids = request.env['res.partner'].browse(map(int, partners))
            if cc_partners:
                email_cc_ids = request.env['res.partner'].browse(map(int, cc_partners))
            if bcc_partners:
                email_bcc_ids = request.env['res.partner'].browse(map(int, bcc_partners))
            # for partner in request.env['res.partner'].browse(map(int, partners)):
            attachment_ids = []
            files = request.httprequest.files.getlist('compose_attachments')
            if files:
                for i in files:
                    if i.filename != '':
                        attachments = {
                                'name': i.filename,
                                'res_name': i.filename,
                                'res_model': model_name or 'res.partner',
                                'res_id': res_id and int(res_id) or False,
                                'datas': base64.encodebytes(i.read()),
                            }
                        attachment = request.env['ir.attachment'].sudo().create(attachments)
                        attachment_ids.append(attachment.id)

            message = message_object.message_post(
                body=body,
                subject=subject,
                email_from='%s <%s>' % (request.env.user.name, request.env.user.email),
                author_id=request.env.user.partner_id.id,
                attachment_ids=attachment_ids,
                partner_ids=partner_ids.ids,
                email_cc_ids=email_cc_ids.ids if email_cc_ids else False,
                email_bcc_ids=email_bcc_ids.ids if email_bcc_ids else False,
                message_type='email',
                subtype_id=request.env.ref('mail.mt_comment').id,
            )

            message.write({'msg_unread': False})
        return request.redirect('/mail/inbox')

    @http.route(['/mail/send/<model("mail.message"):message>',
                 ], type='http', auth="user", website=True)
    def odoo_move_send(self, message=None, **post):
        message = request.env['odoo.inbox'].move_to_send(message)
        return request.redirect('/mail/send')

    @http.route(['/mail/send',
                 '/mail/send/page/<int:page>'
                 ], type='http', auth="user", website=True)
    def odoo_send(self, page=1, **kw):
        domain = [('author_id', '=', request.env.user.partner_id.id), ('message_type', 'in', ['email', 'comment']), ('message_label', '!=', 'trash')]
        return self._render_odoo_message(domain, '/mail/send', page, 'sent', 'sentcolor')

    @http.route(['/mail/filter/partner/<int:partner_id>'], type="http", auth="user", website=True)
    def mail_filter_partner(self, page=1, **kw):
        partner = request.env['res.partner'].sudo().browse(int(kw.get('partner_id')))
        domain = []
        if kw.get('search'):
            domain = ['|', '|', '|',
                      ('subject', 'ilike', kw.get('search')),
                      ('email_from', 'ilike', kw.get('search')),
                      ('body', 'ilike', kw.get('search')),
                      ('tag_ids.name', 'ilike', kw.get('search'))]
            search = kw.get('search')
        else:
            domain = [('message_label', 'in', ['starred', 'inbox'])]

        return self._render_odoo_message(domain, '/mail/inbox', page, 'filter', 'bluecolor', partner=partner)

    @http.route(['/mail/starred/message',
                 ], type='json', auth="user", website=True)
    def message_starred(self, **kw):
        message = request.env['mail.message'].sudo().browse(kw.get('message'))
        if kw.get('action') == 'add':
            message.starred_partner_ids = [(4, request.env.user.partner_id.id)]
            request.env['odoo.inbox'].set_star(kw.get('action'), message)
        if kw.get('action') == 'remove':
            message.starred_partner_ids = [(3, request.env.user.partner_id.id)]
            request.env['odoo.inbox'].set_star(kw.get('action'), message)

    @http.route('/mail/all_mssg_starred', type="json", auth="user", website=True)
    def odoo_all_mssg_starred(self, messg_ids, **kw):
        for mssg in messg_ids:
            message = request.env['mail.message'].sudo().browse(int(mssg))
            if kw.get('action') == 'add':
                message.starred_partner_ids = [(4, request.env.user.partner_id.id)]
                request.env['odoo.inbox'].set_star(kw.get('action'), message)
        return True

    @http.route('/mail/all_mssg_unstarred', type="json", auth="user", website=True)
    def odoo_all_mssg_unstarred(self, messg_ids, **kw):
        for mssg in messg_ids:
            message = request.env['mail.message'].sudo().browse(int(mssg))
            if kw.get('action') == 'remove':
                message.starred_partner_ids = [(3, request.env.user.partner_id.id)]
                request.env['odoo.inbox'].set_star(kw.get('action'), message)
        return True

    @http.route(['/mail/starred',
                 '/mail/starred/page/<int:page>'
                 ], type='http', auth="user", website=True)
    def odoo_starred(self, page=1, **kw):
        domain = [('message_label', '=', 'starred')]
        return self._render_odoo_message(domain, '/mail/starred', page, 'starred', 'starredcolor')

    @http.route(['/mail/starred_move_to_inbox/<model("mail.message"):message>',
                 ], type='http', auth="user", website=True)
    def starred_move_to_inbox(self, message=None, **kw):
        message.message_label = 'inbox'
        return request.redirect('/mail/starred')

    @http.route(['/mail/snoozed',
                 '/mail/snoozed/page/<int:page>'
                 ], type='http', auth="user", website=True)
    def odoo_snoozed(self, page=1, **kw):
        domain = [('message_label', '=', 'snoozed')]
        return self._render_odoo_message(domain, '/mail/snoozed', page, 'snoozed', 'snoozedcolor')

    @http.route(['/mail/snoozed/<model("mail.message"):message>',
                 ], type='http', auth="user", website=True)
    def set_snoozed(self, message=None, your_time=None, **post):
        message.message_label = 'snoozed'
        your_time = str(your_time)
        if your_time == 'today':
            message.snoozed_time = datetime.now() + timedelta(hours=2)
        elif your_time == 'tomorrow':
            message.snoozed_time = datetime.now() + timedelta(days=1)
        elif your_time == 'nexweek':
            message.snoozed_time = datetime.now() + timedelta(days=7)
        if post.get('date'):
            message.snoozed_time = datetime.strptime(str(post.get('date')), "%m/%d/%Y %I:%M %p").strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        return request.redirect('/mail/inbox')

    @http.route(['/mail/all_mssg_snoozed',
                 ], type='json', auth="user", website=True)
    def all_set_snoozed(self, mssg_snooze=None, your_time=None, **post):
        for mssg in mssg_snooze:
            message_id = request.env['mail.message'].sudo().browse(int(mssg))
            message_id.message_label = 'snoozed'
            if your_time == 'today':
                message_id.snoozed_time = datetime.now() + timedelta(hours=2)
            elif your_time == 'tomorrow':
                message_id.snoozed_time = datetime.now() + timedelta(days=1)
            elif your_time == 'nexweek':
                message_id.snoozed_time = datetime.now() + timedelta(days=7)
            # if snooze_date:
            #     message_id.snoozed_time = datetime.strptime(snooze_date, "%m/%d/%Y %I:%M %p").strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        return True

    @http.route(['/mail/all_mssg_snoozed_submit',
                 ], type='json', auth="user", website=True)
    def all_set_snoozed_submit(self, mssg_snooze=None, snooze_date=None, **post):
        for mssg in mssg_snooze:
            message_id = request.env['mail.message'].sudo().browse(int(mssg))
            message_id.message_label = 'snoozed'
            if snooze_date:
                message_id.snoozed_time = datetime.strptime(snooze_date, "%m/%d/%Y %I:%M %p").strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        return True

    @http.route(['/mail/set_done/<model("mail.message"):message>',
                 ], type='http', auth="user", website=True)
    def message_done(self, message=None, **kw):
        request.env['odoo.inbox'].set_done(message)
        return request.redirect('/mail/inbox')

    @http.route(['/mail/done',
                 '/mail/done/page/<int:page>'
                 ], type='http', auth="user", website=True)
    def mail_done(self, page=1, **kw):
        domain = [('message_label', '=', 'done')]
        return self._render_odoo_message(domain, '/mail/done', page, 'done', 'donecolor')

    @http.route(['/mail/move_to_inbox/<model("mail.message"):message>',
                 ], type='http', auth="user", website=True)
    def move_to_inbox(self, message=None, **kw):
        message.message_label = 'inbox'
        return request.redirect('/mail/inbox')

    @http.route([
        '/mail/move_to_trash/<model("mail.message"):message>',
    ], type='http', auth="user", website=True)
    def odoo_move_trash(self, message=None, **post):
        request.env['odoo.inbox'].move_to_trash(message)
        return request.redirect('/mail/inbox')

    @http.route(['/mail/trash',
                 '/mail/trash/page/<int:page>'
                 ], type='http', auth="user", website=True)
    def odoo_trash(self, page=1, **kw):
        domain = [('message_label', '=', 'trash')]
        return self._render_odoo_message(domain, '/mail/trash', page, 'trash', 'trashcolor')

    @http.route(['/mail/delete_forever/<model("mail.message"):message>',
                 ], type='http', auth="user", website=True)
    def delete_forever(self, message=None, **kw):
        message.sudo().unlink()
        return request.redirect('/mail/trash')

    @http.route('/mail/all_mssg_trash', type="json", auth="user", website=True)
    def odoo_all_mssg_trash(self, messg_ids, **post):
        for mssg in messg_ids:
            message_id = request.env['mail.message'].sudo().browse(int(mssg))
            if message_id or message_id.folder_id:
                message_id.write({'folder_id': False,
                                  'message_label': 'trash'
                                  })
        return True

    @http.route('/mail/all_mssg_done', type="json", auth="user", website=True)
    def odoo_all_mssg_done(self, messg_ids, **post):
        for mssg in messg_ids:
            message_id = request.env['mail.message'].sudo().browse(int(mssg))
            if message_id or message_id.folder_id:
                message_id.write({'message_label': 'done'
                                  })
        return True

    @http.route('/mail/attachment/<model("ir.attachment"):attachment>/download', type='http', website=True)
    def slide_download(self, attachment):
        filecontent = base64.b64decode(attachment.datas)
        main_type, sub_type = attachment.mimetype.split('/', 1)
        disposition = 'attachment; filename=%s.%s' % (werkzeug.urls.url_quote(attachment.name), sub_type)
        return request.make_response(
            filecontent,
            [('Content-Type', attachment.mimetype),
             ('Content-Length', len(filecontent)),
             ('Content-Disposition', disposition)])
        return request.render("website.403")

    @http.route('/mail/partner_create', type="json", auth="user", website=True)
    def odoo_partner_create(self, email_address, **post):
        if email_address:
            partner_id = request.env['res.partner'].sudo().search([('name', '=', email_address.split('@')[0]), ('email', '=', email_address)])
            if not partner_id:
                partner_id = request.env['res.partner'].sudo().create({
                    'name': email_address.split('@')[0],
                    'email': email_address
                    })
            return {'success': True, 'partner_id': partner_id.id, 'partner_name': partner_id.name, 'email': partner_id.email}
        else:
            return {'error': 'email address is wrong'}

    @http.route('/mail/message_tag_assign', type="json", auth="user", website=True)
    def odoo_message_tag_assign(self, message_id, tag_ids=[], create_tag_input=None, **post):
        if message_id:
            message = request.env['mail.message'].sudo().browse(message_id)
            user_id = request.env.user
            if create_tag_input:
                new_tag_id = request.env['message.tag'].create({'name': create_tag_input,
                                                                'user_id': user_id.id})
                tag_ids += [new_tag_id.id]
            message.tag_ids = [(6, 0, tag_ids)]
            main_tag_ids = request.env['message.tag'].sudo().search([('user_id', '=', user_id.id)])
            message_tag_list_template = request.env['ir.ui.view']._render_template('odoo_inbox.message_tag_list', {'mail_message': message})
            message_tag_dropdown = request.env['ir.ui.view']._render_template('odoo_inbox.tag_dropdown', {'mail_message': message, 'tag_ids': main_tag_ids})
            return {'success': True, 'message_tag_list': message_tag_list_template, 'message_tag_dropdown': message_tag_dropdown}
        else:
            return {'error': 'Message is not find'}

    @http.route('/mail/message_tag_assign/all', type="json", auth="user", website=True)
    def odoo_message_tag_assign_all(self, message_id=[], tag_ids=[], create_tag_input=None, **post):
        if message_id:
            message_ids = request.env['mail.message'].sudo().browse(message_id)
            user_id = request.env.user
            if create_tag_input:
                new_tag_id = request.env['message.tag'].create({'name': create_tag_input,
                                                                'user_id': user_id.id})
                tag_ids += [new_tag_id.id]
            for message in message_ids:
                tttag_ids = list(set(tag_ids + message.tag_ids.ids))
                message.tag_ids = [(6, 0, tttag_ids)]
            return True
        else:
            return {'error': 'Message is not find'}

    @http.route('/mail/message_tag_delete', type="json", auth="user", website=True)
    def odoo_message_tag_delete(self, message_id, tag_id, **post):
        if message_id and tag_id:
            user_id = request.env.user
            message = request.env['mail.message'].sudo().browse(message_id)
            message.tag_ids = [(3, tag_id)]
            main_tag_ids = request.env['message.tag'].sudo().search([('user_id', '=', user_id.id)])
            message_tag_list_template = request.env['ir.ui.view']._render_template('odoo_inbox.message_tag_list', {'mail_message': message})
            message_tag_dropdown = request.env['ir.ui.view']._render_template('odoo_inbox.tag_dropdown', {'mail_message': message, 'tag_ids': main_tag_ids})
            return {'success': True, 'message_tag_list': message_tag_list_template, 'message_tag_dropdown': message_tag_dropdown}
        else:
            return {'success': False, 'error': 'Message is not find'}

    @http.route(['/mail/tag/<model("message.tag"):tag>',
                 '/mail/tag/<model("message.tag"):tag>/page/<int:page>'], type='http', auth="user", website=True)
    def odoo_tags(self, tag, page=1, **kw):
        domain = [('tag_ids', '=', tag.id)]
        return self._render_odoo_message(domain, '/mail/tag/' + str(tag.id), page, tag.name, 'bluecolor', existing_tag=tag.id)

    @http.route(['/mail/tag_edit'], type='http', auth="user", methods=['POST'], website=True)
    def odoo_tags_edit(self, **kw):
        if kw.get('tag_id') and kw.get('tag_name'):
            tag_id = request.env['message.tag'].sudo().browse(int(kw.get('tag_id')))
            tag_id.name = kw.get('tag_name')
        return request.redirect(request.httprequest.referrer or '/mail/inbox')

    @http.route(['/mail/tag_delete'], type='http', auth="user", methods=['POST'], website=True)
    def odoo_tags_delete(self, **kw):
        if kw.get('tag_id'):
            tag_id = request.env['message.tag'].sudo().browse(int(kw.get('tag_id')))
            tag_id.unlink()
        return request.redirect('/mail/inbox')

    @http.route(['/mail/folder/<model("message.folder"):folder>',
                 '/mail/folder/<model("message.folder"):folder>/page/<int:page>'], type='http', auth="user", website=True)
    def odoo_folders(self, folder, page=1, **kw):
        domain = [('folder_id', '=', folder.id)]
        return self._render_odoo_message(domain, '/mail/folder/' + str(folder.id), page, folder.name, 'bluecolor', existing_folder=folder.id)

    @http.route(['/mail/folder_edit'], type='http', auth="user", methods=['POST'], website=True)
    def odoo_folder_edit(self, **kw):
        if kw.get('folder_id') and kw.get('folder_name'):
            folder_id = request.env['message.folder'].sudo().browse(int(kw.get('folder_id')))
            folder_id.name = kw.get('folder_name')
        return request.redirect(request.httprequest.referrer or '/mail/inbox')

    @http.route(['/mail/folder_delete'], type='http', auth="user", methods=['POST'], website=True)
    def odoo_folder_delete(self, **kw):
        if kw.get('folder_id'):
            folder_id = request.env['message.folder'].sudo().browse(int(kw.get('folder_id')))
            folder_id.unlink()
        return request.redirect('/mail/inbox')

    @http.route(['/mail/move_to_folder/<model("message.folder"):folder>/<model("mail.message"):message>'], type='http', auth="user", website=True)
    def odoo_move_to_folder(self, folder, message, **kw):
        if folder and message:
            message.folder_id = folder.id
        return request.redirect(request.httprequest.referrer or '/mail/inbox')

    @http.route('/mail/all_move_to_folder', type="json", auth="user", website=True)
    def odoo_all_move_to_folder(self, folder_id, messg_ids, **post):
        for mssg in messg_ids:
            message_id = request.env['mail.message'].sudo().browse(int(mssg))
            if folder_id == 'move_to_inbox':
                message_id.write({'folder_id': False, 'message_label': 'inbox',
                                  })
            elif folder_id and message_id:
                message_id.folder_id = folder_id
        return True

    @http.route(['/mail/folder/create'], type='http', auth="user", methods=["POST"], website=True)
    def odoo_new_folder(self, **kw):
        if kw.get('create_folder'):
            user_id = request.env.user.id
            folder_id = request.env['message.folder'].create({'name': kw.get('create_folder'),
                                                              'user_id': user_id})
            if kw.get('message_id') and folder_id:
                message_id = request.env['mail.message'].sudo().browse(int(kw.get('message_id')))
                message_id.folder_id = folder_id.id
        return request.redirect(request.httprequest.referrer or '/mail/inbox')

    @http.route('/mail/get_document_records', type="json", auth="user", website=True)
    def get_document_model_records(self, **kw):
        records_dict = {}
        document_model = kw.get('document_model') if kw.get('document_model') != '0' else False
        if document_model:
            records = request.env[kw.get('document_model')].search([], order="id")
            records_dict = records.name_get()
        return records_dict

    @http.route('/mail/get_document_followers', type="json", auth="user", website=True)
    def get_document_followers(self, **kw):
        followers_dict = []
        if kw.get('document_model') and kw.get('res_id'):
            followers = request.env['mail.followers'].sudo().search([
                        ('res_model', '=', kw.get('document_model')),
                        ('res_id', '=', int(kw.get('res_id')))])
            for follower in followers:
                if follower.partner_id:
                    followers_dict.append({'id': follower.partner_id.id, 'name': follower.partner_id.name})
        return followers_dict

    @http.route('/mail/get_res_partners', type="http", auth="user", methods=['POST', 'GET'], website=True, csrf=False)
    def get_mail_res_partners(self, **kw):
        partner_values = {}
        partner_list = []
        domain = [('email', '!=', False)]
        if kw.get('q'):
            domain += ['|', ('name', 'ilike', kw.get('q')), ('email', 'ilike', kw.get('q'))]
            partner_ids = request.env['res.partner'].search(domain)
            for partner in partner_ids:
                text_name = ''
                if partner.name:
                    text_name += partner.name
                if partner.email:
                    email_name = ' <' + partner.email + '>'
                    text_name += email_name
                partner_list.append({'id': partner.id,
                                     'text': text_name})
        partner_values = {"items": partner_list}
        return json.dumps(partner_values)

    @http.route('/mail/get_mail_templates', type="json", auth="user", website=True)
    def get_mail_templates(self, **kw):
        templates_dict = []
        mail_template_ids = request.env['mail.template'].sudo().search([('model', 'in', ('inbox.mail.template', kw.get('document_model', False)))])
        for mail_template in mail_template_ids:
            templates_dict.append({'id': mail_template.id, 'name': mail_template.name})
        return templates_dict

    @http.route('/mail/get_mail_template_body', type="json", auth="user", website=True)
    def get_mail_template_body(self, **kw):
        template_value = {}
        if kw.get('mail_template_id'):
            template = request.env['mail.template'].with_context(tpl_partners_only=True).browse(int(kw.get('mail_template_id')))
        if kw.get('res_id'):
            res_id = int(kw.get('res_id'))
        else:
            if template and template.model_id and template.model_id.model == 'inbox.mail.template':
                res_id = request.env.ref('odoo_inbox.data_inbox_mail_template').id
        if res_id and template:
            if template:
                fields = ['subject', 'body_html', 'email_from', 'email_to', 'partner_to', 'email_cc',  'reply_to', 'attachment_ids', 'mail_server_id']
                template_values = template.generate_email([res_id], fields=fields)
                template_value = template_values[res_id]
        return template_value

    @http.route('/mail/create_mail_template', type="json", auth="user", website=True)
    def create_mail_template(self, **kw):
        if kw.get('model_name'):
            document_model_name = kw.get('model_name')
        else:
            document_model_name = 'inbox.mail.template'
        subject = kw.get('subject')
        body_html = kw.get('body_html')
        model = request.env['ir.model'].sudo()._get(document_model_name)
        model_name = model.name or ''
        template_name = "%s: %s" % (model_name, tools.ustr(subject))
        values = {
            'name': template_name,
            'subject': subject or False,
            'body_html': body_html or False,
            'model_id': model.id or False,
            # 'attachment_ids': [(6, 0, [att.id for att in record.attachment_ids])],
        }
        template = request.env['mail.template'].create(values)
        _logger.info("Mail Template is created: %s" % [template])
        return True
