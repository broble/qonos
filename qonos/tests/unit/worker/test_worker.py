# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright 2013 Rackspace
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock
import mox
import time

from qonos.common import exception
from qonos.tests.unit import utils as unit_utils
from qonos.tests.unit.worker import fakes
from qonos.tests import utils as test_utils
from qonos.worker import worker


class TestWorker(test_utils.BaseTestCase):
    def setUp(self):
        super(TestWorker, self).setUp()
        self.client_factory = mock.Mock()
        self.client = mock.Mock()
        self.client_factory.return_value = self.client
        self.processor = mock.Mock()
        self.worker = worker.Worker(self.client_factory,
                                    self.processor)

    def tearDown(self):
        super(TestWorker, self).tearDown()

    def test_init_worker(self):
        self.assertFalse(self.worker.pid)
        self.assertFalse(self.worker.running)
        self.client.create_worker.return_value = {"id": 1}

        self.worker.init_worker()

        self.assertEquals(self.worker.worker_id, 1)
        self.assertTrue(self.worker.pid)
        self.assertTrue(self.worker.running)
        self.processor.init_processor.assert_called_once_with(self.worker)
        self.client.create_worker.assert_called_once()

    def test_worker_process_job(self):
        self.worker.process_job(fakes.JOB['job'])
        self.processor.process_job.assert_called_once_with(fakes.JOB['job'])

    def test_worker_process_job_with_exception(self):
        job = fakes.JOB['job']
        self.processor.process_job.side_effect = Exception('Boom!')

        self.worker.process_job(job)

        self.processor.process_job.assert_called_once_with(job)
        self.client.update_job_status.assert_called_once_with(job['id'],
                                                              'ERROR',
                                                              None,
                                                              mock.ANY)

    def test_worker_process_job_with_polling_exception(self):
        job = fakes.JOB['job']
        self.processor.process_job.side_effect = exception. \
                                                 PollingException('Boom!')

        self.worker.process_job(job)

        self.processor.process_job.assert_called_once_with(job)


class TestWorkerWithMox(test_utils.BaseTestCase):
    def setUp(self):
        super(TestWorkerWithMox, self).setUp()
        self.mox = mox.Mox()
        self.client = self.mox.CreateMockAnything()

        def client_factory(*args, **kwargs):
            return self.client

        self.processor = FakeProcessor()
        self.worker = worker.Worker(client_factory,
                                    processor=self.processor)

    def tearDown(self):
        self.mox.UnsetStubs()
        super(TestWorkerWithMox, self).tearDown()

    def prepare_client_mock(self, job=fakes.JOB_NONE, empty_jobs=0):
        self.client.create_worker(mox.IsA(str), mox.IsA(int)).\
            AndReturn(fakes.WORKER)
        # Argh! Mox why you no have "Times(x)" function?!?!
        for i in range(empty_jobs):
            self.client.get_next_job(str(fakes.WORKER_ID), mox.IsA(str)).\
                AndReturn(fakes.JOB_NONE)

        self.client.get_next_job(str(fakes.WORKER_ID), mox.IsA(str)).\
            AndReturn(job)
        self.client.delete_worker(str(fakes.WORKER_ID))

    def test_stop_processor(self):
        self.worker._terminate(42, None)
        self.assertTrue(self.processor.stopping)

    def test_run_loop_no_jobs(self):
        self.prepare_client_mock()
        self.mox.ReplayAll()

        self.config(job_poll_interval=5, group='worker')
        self.config(action_type='snapshot', group='worker')

        fake_sleep = lambda x: None
        self.stubs.Set(time, 'sleep', fake_sleep)

        self.worker.run(run_once=True, poll_once=True)
        self.assertTrue(self.processor.was_init_processor_called(1))
        self.assertTrue(self.processor.was_process_job_called(0))
        self.assertTrue(self.processor.was_cleanup_processor_called(1))

        self.mox.VerifyAll()

    def test_run_loop_with_job(self):
        self.prepare_client_mock(job=fakes.JOB)
        self.mox.ReplayAll()

        self.config(job_poll_interval=5, group='worker')
        self.config(action_type='snapshot', group='worker')

        fake_sleep = lambda x: None
        self.stubs.Set(time, 'sleep', fake_sleep)

        self.worker.run(run_once=True, poll_once=True)
        self.assertTrue(self.processor.was_init_processor_called(1))
        self.assertTrue(self.processor.was_process_job_called(1))
        self.assertTrue(self.processor.was_cleanup_processor_called(1))

        self.mox.VerifyAll()

    def test_run_loop_wait_for_job(self):
        self.prepare_client_mock(job=fakes.JOB, empty_jobs=3)
        self.mox.ReplayAll()

        self.config(job_poll_interval=5, group='worker')
        self.config(action_type='snapshot', group='worker')

        fake_sleep = lambda x: None
        self.stubs.Set(time, 'sleep', fake_sleep)

        self.worker.run(run_once=True, poll_once=False)
        self.assertTrue(self.processor.was_init_processor_called(1))
        self.assertTrue(self.processor.was_process_job_called(1))
        self.assertTrue(self.processor.was_cleanup_processor_called(1))

        self.mox.VerifyAll()

    def test_job_poll_interval(self):
        self.prepare_client_mock(job=fakes.JOB, empty_jobs=0)
        self.mox.ReplayAll()

        poll_interval = 1e-3  # dont want this test to take forever!
        self.config(job_poll_interval=poll_interval, group='worker')
        self.config(action_type='snapshot', group='worker')

        time_before = time.time()

        self.worker.run(run_once=True, poll_once=True)
        self.assertTrue(self.processor.was_init_processor_called(1))
        self.assertTrue(self.processor.was_process_job_called(1))
        self.assertTrue(self.processor.was_cleanup_processor_called(1))

        time_after = time.time()
        time_delta = time_after - time_before
        self.assertTrue(time_delta >= poll_interval)

        self.mox.VerifyAll()

    def test_register_retries_on_error(self):
        self.client.create_worker(mox.IsA(str), mox.IsA(int)).\
            AndRaise(Exception())
        self.client.create_worker(mox.IsA(str), mox.IsA(int)).\
            AndRaise(Exception())
        self.client.create_worker(mox.IsA(str), mox.IsA(int)).\
            AndReturn(fakes.WORKER)
        self.client.get_next_job(str(fakes.WORKER_ID), mox.IsA(str)).\
            AndReturn(fakes.JOB)
        self.client.delete_worker(str(fakes.WORKER_ID))
        self.mox.ReplayAll()

        self.config(job_poll_interval=5, group='worker')
        self.config(action_type='snapshot', group='worker')

        fake_sleep = lambda x: None
        self.stubs.Set(time, 'sleep', fake_sleep)

        self.worker.run(run_once=True, poll_once=True)
        self.assertTrue(self.processor.was_init_processor_called(1))
        self.assertTrue(self.processor.was_process_job_called(1))
        self.assertTrue(self.processor.was_cleanup_processor_called(1))

        self.mox.VerifyAll()

    def test_get_job_retries_on_error(self):
        self.client.create_worker(mox.IsA(str), mox.IsA(int)).\
            AndReturn(fakes.WORKER)
        self.client.get_next_job(str(fakes.WORKER_ID), mox.IsA(str)).\
            AndRaise(Exception())
        self.client.get_next_job(str(fakes.WORKER_ID), mox.IsA(str)).\
            AndRaise(Exception())
        self.client.get_next_job(str(fakes.WORKER_ID), mox.IsA(str)).\
            AndReturn(fakes.JOB)
        self.client.delete_worker(str(fakes.WORKER_ID))
        self.mox.ReplayAll()

        self.config(job_poll_interval=5, group='worker')
        self.config(action_type='snapshot', group='worker')

        fake_sleep = lambda x: None
        self.stubs.Set(time, 'sleep', fake_sleep)

        self.worker.run(run_once=True, poll_once=False)
        self.assertTrue(self.processor.was_init_processor_called(1))
        self.assertTrue(self.processor.was_process_job_called(1))
        self.assertTrue(self.processor.was_cleanup_processor_called(1))

        self.mox.VerifyAll()

    def test_error_reported_when_processing_job(self):
        self.prepare_client_mock(job=fakes.JOB)

        def fake_process_job(*args, **kwargs):
            raise Exception()

        self.stubs.Set(self.processor, 'process_job', fake_process_job)

        self.client.update_job(mox.IsA(str),
                               'ERROR',
                               error_message=mox.IsA(str))
        self.mox.ReplayAll()

        fake_sleep = lambda x: None
        self.stubs.Set(time, 'sleep', fake_sleep)

        self.worker.run(run_once=True, poll_once=True)

        self.mox.VerifyAll()

    def test_unregister_does_not_retry_on_error(self):
        self.client.create_worker(mox.IsA(str), mox.IsA(int)).\
            AndReturn(fakes.WORKER)
        self.client.get_next_job(str(fakes.WORKER_ID), mox.IsA(str)).\
            AndReturn(fakes.JOB)
        self.client.delete_worker(str(fakes.WORKER_ID)).AndRaise(Exception())
        self.mox.ReplayAll()

        self.config(job_poll_interval=5, group='worker')
        self.config(action_type='snapshot', group='worker')

        fake_sleep = lambda x: None
        self.stubs.Set(time, 'sleep', fake_sleep)

        self.worker.run(run_once=True, poll_once=True)
        self.assertTrue(self.processor.was_init_processor_called(1))
        self.assertTrue(self.processor.was_process_job_called(1))
        self.assertTrue(self.processor.was_cleanup_processor_called(1))

        self.mox.VerifyAll()

    def test_update_job(self):
        status = 'PROCESSING'
        self.client.update_job_status(unit_utils.JOB_UUID1, status,
                                      None, None).AndReturn(fakes.WORKER)
        self.mox.ReplayAll()

        self.worker.update_job(unit_utils.JOB_UUID1, status)

        self.mox.VerifyAll()

    def test_update_job_with_timeout(self):
        status = 'ERROR'
        timeout = 'blah'
        self.client.update_job_status(unit_utils.JOB_UUID1, status,
                                      timeout, None).AndReturn(fakes.WORKER)
        self.mox.ReplayAll()

        self.worker.update_job(unit_utils.JOB_UUID1, status, timeout=timeout)

        self.mox.VerifyAll()

    def test_update_job_with_error_message(self):
        status = 'ERROR'
        error_message = 'blah'
        self.client.update_job_status(unit_utils.JOB_UUID1,
                                      status,
                                      None,
                                      error_message).AndReturn(fakes.WORKER)
        self.mox.ReplayAll()

        self.worker.update_job(unit_utils.JOB_UUID1,
                               status,
                               error_message=error_message)

        self.mox.VerifyAll()

    def test_update_job_with_exception(self):
        status = 'PROCESSING'
        self.client.update_job_status(unit_utils.JOB_UUID1,
                                      status,
                                      None, None).AndRaise(Exception)
        self.mox.ReplayAll()

        self.worker.update_job(unit_utils.JOB_UUID1, status)

        self.mox.VerifyAll()


class FakeProcessor(worker.JobProcessor):

    def __init__(self):
        self.init_processor_called = 0
        self.process_job_called = 0
        self.cleanup_processor_called = 0
        super(FakeProcessor, self).__init__()

    def init_processor(self, worker):
        super(FakeProcessor, self).init_processor(worker)
        self.init_processor_called += 1

    def process_job(self, job):
        self.process_job_called += 1

    def cleanup_processor(self):
        self.cleanup_processor_called += 1

    def was_init_processor_called(self, times):
        return self.init_processor_called == times

    def was_process_job_called(self, times):
        return self.process_job_called == times

    def was_cleanup_processor_called(self, times):
        return self.cleanup_processor_called == times
