#!/usr/bin/python
# Copyright (c) 2010 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Smoke tests for gclient.py.

Shell out 'gclient' and run basic conformance tests.

This test assumes GClientSmokeBase.URL_BASE is valid.
"""

import logging
import os
import pprint
import shutil
import subprocess
import sys
import unittest

from fake_repos import rmtree, write, FakeRepos

join = os.path.join

SHOULD_LEAK = False
UNITTEST_DIR = os.path.abspath(os.path.dirname(__file__))
GCLIENT_PATH = join(os.path.dirname(UNITTEST_DIR), 'gclient')
# all tests outputs goes there.
TRIAL_DIR = join(UNITTEST_DIR, '_trial')
# In case you want to use another machine to create the fake repos, e.g.
# not on Windows.
HOST = '127.0.0.1'
FAKE = None


def read_tree(tree_root):
  """Returns a dict of all the files in a tree."""
  tree = {}
  for root, dirs, files in os.walk(tree_root):
    for d in filter(lambda x: x.startswith('.'), dirs):
      dirs.remove(d)
    for f in [join(root, f) for f in files if not f.startswith('.')]:
      tree[f[len(tree_root) + 1:]] = open(join(root, f), 'rb').read()
  return tree


def dict_diff(dict1, dict2):
  diff = {}
  for k, v in dict1.iteritems():
    if k not in dict2:
      diff[k] = v
    elif v != dict2[k]:
      diff[k] = (v, dict2[k])
  for k, v in dict2.iteritems():
    if k not in dict1:
      diff[k] = v
  return diff


def mangle_svn_tree(*args):
  result = {}
  for old_root, new_root, tree in args:
    for k, v in tree.iteritems():
      if not k.startswith(old_root):
        continue
      result[join(new_root, k[len(old_root) + 1:])] = v
  return result


def mangle_git_tree(*args):
  result = {}
  for new_root, tree in args:
    for k, v in tree.iteritems():
      result[join(new_root, k)] = v
  return result


class GClientSmokeBase(unittest.TestCase):
  # This subversion repository contains a test repository.
  ROOT_DIR = join(TRIAL_DIR, 'smoke')

  def setUp(self):
    # Vaguely inspired by twisted.
    # Make sure it doesn't try to auto update when testing!
    self.env = os.environ.copy()
    self.env['DEPOT_TOOLS_UPDATE'] = '0'
    # Remove left overs
    self.root_dir = join(self.ROOT_DIR, self.id())
    rmtree(self.root_dir)
    if not os.path.exists(self.ROOT_DIR):
      os.mkdir(self.ROOT_DIR)
    os.mkdir(self.root_dir)
    self.svn_base = 'svn://%s/svn/' % HOST
    self.git_base = 'git://%s/git/' % HOST

  def tearDown(self):
    if not SHOULD_LEAK:
      rmtree(self.root_dir)

  def gclient(self, cmd, cwd=None):
    if not cwd:
      cwd = self.root_dir
    process = subprocess.Popen([GCLIENT_PATH] + cmd, cwd=cwd, env=self.env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        shell=sys.platform.startswith('win'))
    (stdout, stderr) = process.communicate()
    return (stdout, stderr, process.returncode)

  def check(self, expected, results):
    def checkString(expected, result):
      if expected != result:
        while expected and result and expected[0] == result[0]:
          expected = expected[1:]
          result = result[1:]
      self.assertEquals(expected, result)
    checkString(expected[0], results[0])
    checkString(expected[1], results[1])
    self.assertEquals(expected[2], results[2])

  def assertTree(self, tree):
    actual = read_tree(self.root_dir)
    diff = dict_diff(tree, actual)
    if diff:
      logging.debug('Actual %s\n%s' % (self.root_dir, pprint.pformat(actual)))
      logging.debug('Expected\n%s' % pprint.pformat(tree))
      logging.debug('Diff\n%s' % pprint.pformat(diff))
    self.assertEquals(tree, actual)


class GClientSmoke(GClientSmokeBase):
  def testCommands(self):
    """This test is to make sure no new command was added."""
    result = self.gclient(['help'])
    self.assertEquals(3189, len(result[0]))
    self.assertEquals(0, len(result[1]))
    self.assertEquals(0, result[2])

  def testNotConfigured(self):
    res = ('', 'Error: client not configured; see \'gclient config\'\n', 1)
    self.check(res, self.gclient(['cleanup']))
    self.check(res, self.gclient(['diff']))
    self.check(res, self.gclient(['export', 'foo']))
    self.check(res, self.gclient(['pack']))
    self.check(res, self.gclient(['revert']))
    self.check(res, self.gclient(['revinfo']))
    self.check(res, self.gclient(['runhooks']))
    self.check(res, self.gclient(['status']))
    self.check(res, self.gclient(['sync']))
    self.check(res, self.gclient(['update']))


class GClientSmokeSVN(GClientSmokeBase):
  """sync is the most important command. Hence test it more."""
  def testSync(self):
    """Test pure gclient svn checkout, example of Chromium checkout"""
    self.gclient(['config', self.svn_base + 'trunk/src/'])
    # Test unversioned checkout.
    results = self.gclient(['sync', '--deps', 'mac'])
    logging.debug(results[0])
    self.assertEquals('', results[1])
    self.assertEquals(0, results[2])
    tree = mangle_svn_tree(
        (join('trunk', 'src'), 'src', FAKE.svn_revs[-1]),
        (join('trunk', 'third_party', 'foo'), join('src', 'third_party', 'foo'),
            FAKE.svn_revs[1]),
        (join('trunk', 'other'), join('src', 'other'), FAKE.svn_revs[2]),
        )
    self.assertTree(tree)

    # Test incremental versioned sync: sync backward.
    results = self.gclient(['sync', '--revision', 'src@1', '--deps', 'mac',
                            '--delete_unversioned_trees'])
    logging.debug(results[0])
    self.assertEquals('', results[1])
    self.assertEquals(0, results[2])
    tree = mangle_svn_tree(
        (join('trunk', 'src'), 'src', FAKE.svn_revs[1]),
        (join('trunk', 'third_party', 'foo'), join('src', 'third_party', 'fpp'),
            FAKE.svn_revs[2]),
        (join('trunk', 'other'), join('src', 'other'), FAKE.svn_revs[2]),
        (join('trunk', 'third_party', 'foo'),
            join('src', 'third_party', 'prout'),
            FAKE.svn_revs[2]),
        )
    self.assertTree(tree)
    # Test incremental sync: delete-unversioned_trees isn't there.
    results = self.gclient(['sync', '--deps', 'mac'])
    logging.debug(results[0])
    self.assertEquals('', results[1])
    self.assertEquals(0, results[2])
    tree = mangle_svn_tree(
        (join('trunk', 'src'), 'src', FAKE.svn_revs[-1]),
        (join('trunk', 'third_party', 'foo'), join('src', 'third_party', 'fpp'),
            FAKE.svn_revs[2]),
        (join('trunk', 'third_party', 'foo'), join('src', 'third_party', 'foo'),
            FAKE.svn_revs[1]),
        (join('trunk', 'other'), join('src', 'other'), FAKE.svn_revs[2]),
        (join('trunk', 'third_party', 'foo'),
            join('src', 'third_party', 'prout'),
            FAKE.svn_revs[2]),
        )
    self.assertTree(tree)

  def testRevertAndStatus(self):
    self.gclient(['config', self.svn_base + 'trunk/src/'])
    results = self.gclient(['sync', '--deps', 'mac'])
    write(join(self.root_dir, 'src', 'third_party', 'foo', 'hi'), 'Hey!')

    results = self.gclient(['status'])
    out = results[0].splitlines(False)
    self.assertEquals(7, len(out))
    self.assertEquals(out[0], '')
    self.assertTrue(out[1].startswith('________ running \'svn status\' in \''))
    self.assertEquals(out[2], '?       other')
    self.assertEquals(out[3], '?       third_party/foo')
    self.assertEquals(out[4], '')
    self.assertTrue(out[5].startswith('________ running \'svn status\' in \''))
    self.assertEquals(out[6], '?       hi')
    self.assertEquals('', results[1])
    self.assertEquals(0, results[2])

    results = self.gclient(['revert'])
    self.assertEquals('', results[1])
    self.assertEquals(0, results[2])
    tree = mangle_svn_tree(
        (join('trunk', 'src'), 'src', FAKE.svn_revs[-1]),
        (join('trunk', 'third_party', 'foo'), join('src', 'third_party', 'foo'),
            FAKE.svn_revs[1]),
        (join('trunk', 'other'), join('src', 'other'), FAKE.svn_revs[2]),
        )
    self.assertTree(tree)

    results = self.gclient(['status'])
    out = results[0].splitlines(False)
    self.assertEquals(4, len(out))
    self.assertEquals(out[0], '')
    self.assertTrue(out[1].startswith('________ running \'svn status\' in \''))
    self.assertEquals(out[2], '?       other')
    self.assertEquals(out[3], '?       third_party/foo')
    self.assertEquals('', results[1])
    self.assertEquals(0, results[2])


class GClientSmokeGIT(GClientSmokeBase):
  def testSyncGit(self):
    """Test pure gclient git checkout, example of Chromium OS checkout"""
    self.gclient(['config', self.git_base + 'repo_1', '--name', 'src'])
    # Test unversioned checkout.
    results = self.gclient(['sync', '--deps', 'mac'])
    logging.debug(results[0])
    self.assertTrue(results[1].startswith('Switched to a new branch \''))
    self.assertEquals(0, results[2])
    tree = mangle_git_tree(
        ('src', FAKE.git_hashes['repo_1'][1][1]),
        (join('src', 'repo2'), FAKE.git_hashes['repo_2'][0][1]),
        (join('src', 'repo2', 'repo_renamed'), FAKE.git_hashes['repo_3'][1][1]),
        )
    self.assertTree(tree)

    # Test incremental versioned sync: sync backward.
    results = self.gclient(['sync', '--revision',
                            'src@' + FAKE.git_hashes['repo_1'][0][0],
                            '--deps', 'mac', '--delete_unversioned_trees'])
    logging.debug(results[0])
    self.assertEquals('', results[1])
    self.assertEquals(0, results[2])
    tree = mangle_git_tree(
        ('src', FAKE.git_hashes['repo_1'][0][1]),
        (join('src', 'repo2'), FAKE.git_hashes['repo_2'][1][1]),
        (join('src', 'repo2', 'repo3'), FAKE.git_hashes['repo_3'][1][1]),
        (join('src', 'repo4'), FAKE.git_hashes['repo_4'][1][1]),
        )
    self.assertTree(tree)
    # Test incremental sync: delete-unversioned_trees isn't there.
    results = self.gclient(['sync', '--deps', 'mac'])
    logging.debug(results[0])
    self.assertEquals('', results[1])
    self.assertEquals(0, results[2])
    tree = mangle_git_tree(
        ('src', FAKE.git_hashes['repo_1'][1][1]),
        (join('src', 'repo2'), FAKE.git_hashes['repo_2'][1][1]),
        (join('src', 'repo2', 'repo3'), FAKE.git_hashes['repo_3'][1][1]),
        (join('src', 'repo2', 'repo_renamed'), FAKE.git_hashes['repo_3'][1][1]),
        (join('src', 'repo4'), FAKE.git_hashes['repo_4'][1][1]),
        )
    self.assertTree(tree)

  def testRevertAndStatus(self):
    """TODO(maruel): Remove this line once this test is fixed."""
    self.gclient(['config', self.git_base + 'repo_1', '--name', 'src'])
    results = self.gclient(['sync', '--deps', 'mac'])
    write(join(self.root_dir, 'src', 'repo2', 'hi'), 'Hey!')

    results = self.gclient(['status'])
    out = results[0].splitlines(False)
    # TODO(maruel): THIS IS WRONG.
    self.assertEquals(0, len(out))

    results = self.gclient(['revert'])
    self.assertEquals('', results[1])
    self.assertEquals(0, results[2])
    tree = mangle_git_tree(
        ('src', FAKE.git_hashes['repo_1'][1][1]),
        (join('src', 'repo2'), FAKE.git_hashes['repo_2'][0][1]),
        (join('src', 'repo2', 'repo_renamed'), FAKE.git_hashes['repo_3'][1][1]),
        )
    # TODO(maruel): THIS IS WRONG.
    tree[join('src', 'repo2', 'hi')] = 'Hey!'
    self.assertTree(tree)

    results = self.gclient(['status'])
    out = results[0].splitlines(False)
    # TODO(maruel): THIS IS WRONG.
    self.assertEquals(0, len(out))


class GClientSmokeRevInfo(GClientSmokeBase):
  """revert is the second most important command. Hence test it more."""
  def setUp(self):
    GClientSmokeBase.setUp(self)
    self.gclient(['config', self.URL_BASE])


if __name__ == '__main__':
  if '-v' in sys.argv:
    logging.basicConfig(level=logging.DEBUG)
  if '-l' in sys.argv:
    SHOULD_LEAK = True
    sys.argv.remove('-l')
  FAKE = FakeRepos(TRIAL_DIR, SHOULD_LEAK, True)
  try:
    FAKE.setUp()
    unittest.main()
  finally:
    FAKE.tearDown()