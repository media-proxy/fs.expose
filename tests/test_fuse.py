# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals

import errno
import functools
import os
import posix
import textwrap
import tempfile
import multiprocessing
import time
import unittest

import fs
import fuse
import six

from fs.test import FSTestCases
from fs.expose.fuse.operations import PyfilesystemFuseOperations


class _TestFuseMount(FSTestCases):

    _source_url = NotImplemented

    def make_fs(self):
        self.mountpoint = tempfile.mkdtemp()
        self.source_fs = fs.open_fs(self._source_url)
        self.fuse_process = multiprocessing.Process(
            target=fuse.FUSE,
            args=(PyfilesystemFuseOperations(self.source_fs), self.mountpoint),
            kwargs={"foreground": True, "debug": False},
        )
        self.fuse_process.start()
        time.sleep(0.1)
        test_fs = fs.open_fs(self.mountpoint)
        self.assertTrue(test_fs.isempty('/'))
        return test_fs

    def destroy_fs(self, fs):
        fs.close()
        self.fuse_process.terminate()
        self.source_fs.removetree('/')
        self.source_fs.close()
        self.fuse_process.join()
        os.rmdir(self.mountpoint)

    def test_mounted(self):
        with open("/etc/mtab") as f:
            self.assertIn(self.mountpoint, f.read())

# @unittest.skipIf(True, "")
class TestFuseMemFS(_TestFuseMount, unittest.TestCase):
    _source_url = "mem://"

class TestFuseMountTempFS(_TestFuseMount, unittest.TestCase):
    _source_url = "temp://"




class TestAtomicOperations(unittest.TestCase):

    def setUp(self):
        self.fs = fs.open_fs('mem://')
        self.ops = PyfilesystemFuseOperations(self.fs)

    def test_create(self):
        self.assertFalse(self.fs.exists('file.txt'))
        # Normal behaviour
        fd = self.ops('create', 'file.txt', 0)
        self.assertEqual(fd, 0)
        self.assertTrue(self.fs.exists('file.txt'))
        fd2 = self.ops('create', 'file.txt', 0)
        self.assertEqual(fd2, 1)
        # Error when the file exists in exclusive mode
        with self.assertRaises(OSError) as ctx:
            self.ops('create', 'file.txt', posix.O_EXCL)
        self.assertEqual(ctx.exception.errno, errno.EEXIST)
        # Error when creating an existing directory
        self.fs.makedir('/dir')
        with self.assertRaises(OSError) as ctx:
            self.ops('create', 'dir', 0)
        self.assertEqual(ctx.exception.errno, errno.EISDIR)

    def test_truncate(self):
        # Normal behaviour
        self.fs.settext('file.txt', 'Hello, World !')
        self.ops('truncate', 'file.txt', 5)
        self.assertEqual(self.fs.gettext('file.txt'), 'Hello')
        # Normal behaviour on open file
        fd = self.ops.open('file.txt', 0)
        self.ops('truncate', 'file.txt', 2, fd)
        self.assertEqual(self.fs.gettext('file.txt'), 'He')
        # Normal behaviour when extending file
        self.ops('truncate', 'file.txt', 4, fd)
        self.assertEqual(self.fs.gettext('file.txt'), 'He\0\0')
        # Error on unknown descriptor
        with self.assertRaises(OSError) as ctx:
            self.ops('truncate', 'file.txt', 0, 5)
        self.assertEqual(ctx.exception.errno, errno.EBADF)
        # Error when fd does not refer to path
        # Requires _MemoryFile.name attribute
        # with self.assertRaises(OSError) as ctx:
        #     self.ops('truncate', 'dir', 0, fd)
        # self.assertEqual(ctx.exception.errno, errno.EBADF)
        # Error when trying to truncate a directory
        self.fs.makedir('dir')
        with self.assertRaises(OSError) as ctx:
            self.ops('truncate', 'dir', 0)
        self.assertEqual(ctx.exception.errno, errno.EISDIR)
