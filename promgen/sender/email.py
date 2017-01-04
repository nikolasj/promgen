import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from promgen.celery import wrap_send
from promgen.sender import SenderBase

logger = logging.getLogger(__name__)


@wrap_send
class SenderEmail(SenderBase):
    def _send(self, address, alert, data):
        subject = render_to_string('promgen/sender/email.subject.txt', {
            'alert': alert,
            'externalURL': data['externalURL'],
        }).strip()

        body = render_to_string('promgen/sender/email.body.txt', {
            'alert': alert,
            'externalURL': data['externalURL'],
        }).strip()

        send_mail(
            subject,
            body,
            settings.PROMGEN[__name__]['sender'],
            [address]
        )
        return True
