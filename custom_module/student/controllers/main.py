from odoo import http

class MyCustomController(http.Controller):
    @http.route('/my/custom/page', type='http', auth='public', website=True)
    def custom_page(self, **kwargs):
        return http.request.render('student')
