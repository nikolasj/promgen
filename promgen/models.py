import json
import time

from django.contrib.contenttypes.fields import (GenericForeignKey,
                                                GenericRelation)
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from promgen import plugins

FARM_DEFAULT = 'default'


class Sender(models.Model):
    sender = models.CharField(max_length=128)
    value = models.CharField(max_length=128)
    alias = models.CharField(max_length=128, blank=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, limit_choices_to=(
        models.Q(app_label='promgen', model='project') | models.Q(app_label='promgen', model='service'))
    )
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    def show_value(self):
        if self.alias:
            return self.alias
        return self.value

    show_value.short_description = 'Value'

    def __str__(self):
        return '{}:{}'.format(self.sender, self.show_value())


class Service(models.Model):
    name = models.CharField(max_length=128, unique=True)
    sender = GenericRelation(Sender)

    class Meta:
        ordering = ['name']

    def get_absolute_url(self):
        return reverse('service-detail', kwargs={'pk': self.pk})

    def __str__(self):
        return self.name


class Project(models.Model):
    name = models.CharField(max_length=128, unique=True)
    service = models.ForeignKey('Service', on_delete=models.CASCADE)
    farm = models.ForeignKey('Farm', blank=True, null=True, on_delete=models.SET_NULL)
    sender = GenericRelation(Sender)

    class Meta:
        ordering = ['name']

    def get_absolute_url(self):
        return reverse('project-detail', kwargs={'pk': self.pk})

    def __str__(self):
        return '{} [{}]'.format(self.name, self.service.name)


class Farm(models.Model):
    name = models.CharField(max_length=128)
    source = models.CharField(max_length=128)

    class Meta:
        ordering = ['name']
        unique_together = (('name', 'source',))

    def refresh(self):
        remaining = [host.name for host in self.host_set.all()]
        keep = []
        create = []

        for entry in plugins.remotes():
            if self.source == entry.name:
                for host in entry.load().fetch(self.name):
                    if host in remaining:
                        keep.append(host)
                        remaining.remove(host)
                    else:
                        keep.append(host)
                        create.append(host)
                        Host.objects.create(name=host, farm=self)

        if remaining:
            Host.objects.filter(farm=self, name__in=remaining).delete()

    @classmethod
    def fetch(cls, source):
        for entry in plugins.remotes():
            if entry.name == source:
                for farm in entry.load().farms():
                    yield farm

    def __str__(self):
        return '{} ({})'.format(self.name, self.source)


class Host(models.Model):
    name = models.CharField(max_length=128)
    farm = models.ForeignKey('Farm', on_delete=models.CASCADE)

    class Meta:
        ordering = ['name']
        unique_together = (('name', 'farm'))

    def __str__(self):
        return '{} [{}]'.format(self.name, self.farm.name)


class Exporter(models.Model):
    job = models.CharField(max_length=128)
    port = models.IntegerField()
    path = models.CharField(max_length=128, blank=True)
    project = models.ForeignKey('Project', on_delete=models.CASCADE)

    class Meta:
        ordering = ['job', 'port']
        unique_together = (('job', 'port', 'project'))

    def __str__(self):
        return '{}:{}:{} ({})'.format(self.job, self.port, self.path, self.project)

    def get_absolute_url(self):
        return reverse('project-detail', kwargs={'pk': self.project.pk})


class URL(models.Model):
    url = models.URLField(max_length=256)
    project = models.ForeignKey('Project', on_delete=models.CASCADE)


def validate_json_or_empty(value):
    if value == '':
        return
    try:
        json.loads(value)
    except:
        raise ValidationError('Requires json value')


class Rule(models.Model):
    name = models.CharField(max_length=128, unique=True)
    clause = models.TextField()
    duration = models.CharField(max_length=128, choices=[
        ('1s', '1s'),
        ('1m', '1m'),
        ('5m', '5m'),
    ])
    labels = models.TextField(validators=[validate_json_or_empty])
    annotations = models.TextField(validators=[validate_json_or_empty])
    service = models.ForeignKey('Service', on_delete=models.CASCADE)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return '{} [{}]'.format(self.name, self.service.name)

    def get_absolute_url(self):
        return reverse('rule-edit', kwargs={'pk': self.pk})

    def copy_to(self, service):
        '''
        Make a copy under a new service

        It's important that we set pk to None so a new object is created, but we
        also need to ensure the new name is unique by appending some unique data
        to the end of the name
        '''
        self.pk = None
        self.name += str(int(time.time()))
        self.service = service
        self.enabled = False
        self.save()
        return self


class Audit(models.Model):
    body = models.TextField()
    created = models.DateTimeField()

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveIntegerField(default=0)
    content_object = GenericForeignKey('content_type', 'object_id')

    @classmethod
    def log(cls, body, instance=None):
        kwargs = {'body': body, 'created': timezone.now()}
        if instance:
            kwargs['content_type'] = ContentType.objects.get_for_model(instance)
            kwargs['object_id'] = instance.id

        return cls.objects.create(**kwargs)
