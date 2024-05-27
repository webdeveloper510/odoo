from odoo import models, fields

class StudentModel(models.Model):
    _name = 'wb.student'
    _description = 'My Model'

    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
