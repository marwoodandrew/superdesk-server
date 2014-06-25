'''
Created on May 23, 2014

@author: Ioan v. Pocol
'''

from celery.canvas import chord
import flask

import superdesk
from superdesk.io import providers

from .utc import utc, utcnow
from superdesk.celery_app import celery, finish_task_for_progress,\
    finish_subtask_from_progress, add_subtask_to_progress
from celery.result import AsyncResult
from flask.globals import current_app as app
from .items import import_rendition, import_media


def update_status(task_id, current, total):
    archive_item.update_state(task_id, state='PROGRESS', meta={'current': current, 'total': total})


@celery.task()
def archive_media(task_id, guid, href):
    update_status(*add_subtask_to_progress(task_id))
    import_media(guid, href)
    update_status(*finish_subtask_from_progress(task_id))


@celery.task()
def archive_rendition(task_id, guid, name, href):
    update_status(*add_subtask_to_progress(task_id))
    import_rendition(guid, name, href)
    update_status(*finish_subtask_from_progress(task_id))


@celery.task()
def update_item(result, is_main_task, task_id, guid):
    # update import status as done
    data = app.data
    data.update('archive', guid, {"task_id": ""})

    if is_main_task:
        update_status(*finish_task_for_progress(task_id))


@celery.task()
def archive_item(guid, provider_id, user, task_id=None):
    data = app.data
    crt_task_id = archive_item.request.id
    if not task_id:
        task_id = crt_task_id

    update_status(*add_subtask_to_progress(task_id))

    provider = data.find_one('ingest_providers', _id=provider_id)
    service_provider = providers[provider.get('type')]
    service_provider.provider = provider

    item = None
    try:
        items = service_provider.get_items(guid)
    except Exception:
        # TODO: if ingest not available save error on task result
        # if service is not available set a retry and update task status
        return

    for item_it in items:
        if item_it['guid'] == guid:
            item = item_it
            break

    if item is None:
        # TODO: save error on task result
        return

    item['created'] = item['firstcreated'] = utc.localize(item['firstcreated'])
    item['updated'] = item['versioncreated'] = utc.localize(item['versioncreated'])
    data.update('archive', guid, item)

    tasks = []

    for group in item.get('groups', []):
        for ref in group.get('refs', []):
            if 'residRef' in ref:
                doc = {'guid': ref.get('residRef'), 'provider': provider, 'user': user, 'task_id': crt_task_id}

                archived_doc = data.find_one('archive', guid=doc.get('guid'))
                # check if task already started
                if not archived_doc:
                    doc.setdefault('_id', doc.get('guid'))
                    data.insert('archive', [doc])
                elif archived_doc.get('task_id') == crt_task_id:
                    # it is a retry so continue
                    archived_doc.update(doc)
                    data.update('archive', archived_doc)
                else:
                    # there is a cyclic dependency, skip it
                    continue

                ingest_set_archived(doc.get('guid'))
                tasks.append(archive_item.s(task_id, ref['residRef'], provider))

    for rendition in item.get('renditions', {}).values():
        href = service_provider.prepare_href(rendition['href'])
        if rendition['rendition'] == 'baseImage':
            tasks.append(archive_media.s(task_id, guid, href))
        else:
            tasks.append(archive_rendition.s(task_id, guid, rendition['rendition'], href))

    if tasks:
        chord((task for task in tasks), update_item.s(crt_task_id == task_id, task_id, guid)).delay()

    update_status(*finish_subtask_from_progress(task_id))
    if not tasks and task_id == crt_task_id:
        update_status(*finish_task_for_progress(task_id))


def ingest_set_archived(guid):
    ingest_doc = app.data.find_one('ingest', guid=guid)
    if ingest_doc:
        app.data.update('ingest', ingest_doc.get('_id'), {'archived': utcnow()})


def archive_ingest(data, docs, **kwargs):
    data = app.data
    for doc in docs:
        ingest_doc = data.find_one('ingest', guid=doc.get('guid'))
        if not ingest_doc:
            continue
        ingest_set_archived(doc.get('guid'))

        doc.setdefault('_id', doc.get('guid'))
        doc.setdefault('user', str(getattr(flask.g, 'user', {}).get('_id')))
        data.insert('archive', [doc])

        task = archive_item.delay(doc.get('guid'), ingest_doc.get('ingest_provider'), doc.get('user'))
        doc['task_id'] = task.id
        data.update('archive', doc.get('guid'), {"task_id": task.id})
    return [doc.get('guid') for doc in docs]


def archive_ingest_progress(data, req, **lookup):
    try:
        task_id = lookup["task_id"]
        task = AsyncResult(task_id)

        if task.result:
            doc = task.result
        else:
            doc = {}

        if task.state:
            doc['state'] = task.state
        doc['task_id'] = task_id
        doc['_id'] = task_id

        return doc
    except Exception:
        msg = 'No progress information is available for task_id: %s' % task_id
        raise superdesk.SuperdeskError(payload=msg)


superdesk.connect('impl_insert:archive_ingest', archive_ingest)
superdesk.connect('impl_find_one:archive_ingest', archive_ingest_progress)

superdesk.domain('archive_ingest', {
    'url': 'archive_ingest',
    'resource_title': 'archive_ingest',
    'resource_methods': ['POST'],
    'item_methods': ['GET'],
    'additional_lookup': {
        'url': 'regex("[\w-]+")',
        'field': 'task_id'
    },
    'schema': {
        'guid': {
            'type': 'string',
            'required': True,
        },
        'task_id': {
            'type': 'string',
            'required': False,
        },
    },
    'datasource': {
        'backend': 'noop'
    }
})