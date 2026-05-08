"""End-to-end MCP server tests via subprocess + JSON-RPC over stdio."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import date, timedelta


def _setup_repo(path):
    subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=path, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=path, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=path, check=True)


class TestMCP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = os.path.join(os.path.dirname(__file__), 'mcp_server.py')

    def setUp(self):
        self.repo_path = tempfile.mkdtemp(prefix='lazy-mcp-test-')
        _setup_repo(self.repo_path)
        self.env = {
            **os.environ,
            'LAZY_HOME': self.repo_path,
            'LAZY_NO_REMOTE': '1',
        }

    def tearDown(self):
        shutil.rmtree(self.repo_path, ignore_errors=True)

    def _exchange(self, requests):
        payload = "\n".join(json.dumps(r) for r in requests) + "\n"
        proc = subprocess.run(
            ['python3', self.server],
            input=payload, capture_output=True, text=True, env=self.env, timeout=10
        )
        responses = []
        for line in proc.stdout.strip().splitlines():
            if line:
                responses.append(json.loads(line))
        return responses

    def _call_tool(self, name, arguments=None):
        responses = self._exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
             "params": {"name": name, "arguments": arguments or {}}}
        ])
        self.assertEqual(len(responses), 1)
        return responses[0]

    def test_initialize(self):
        r = self._exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        ])[0]
        self.assertEqual(r['id'], 1)
        self.assertIn('serverInfo', r['result'])
        self.assertEqual(r['result']['serverInfo']['name'], 'lazy-mcp')

    def test_tools_list_advertises_all(self):
        r = self._exchange([
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        ])[0]
        names = {t['name'] for t in r['result']['tools']}
        self.assertEqual(names, {
            'lazy_add', 'lazy_list', 'lazy_done',
            'lazy_rename', 'lazy_move', 'lazy_push', 'lazy_get_messages'
        })

    def test_lazy_add_then_list(self):
        r = self._call_tool('lazy_add', {'description': 'mcp task', 'due_date': 'today'})
        self.assertIn('mcp task', r['result']['content'][0]['text'])
        r = self._call_tool('lazy_list')
        self.assertIn('mcp task', r['result']['content'][0]['text'])

    def test_lazy_done(self):
        self._call_tool('lazy_add', {'description': 'finish me', 'due_date': 'today'})
        r = self._call_tool('lazy_done', {'id': 1})
        self.assertIn('finish me', r['result']['content'][0]['text'])
        self.assertIn('done', r['result']['content'][0]['text'].lower())

    def test_lazy_rename_dispatched(self):
        """B1 regression: lazy_rename was declared but never dispatched."""
        self._call_tool('lazy_add', {'description': 'old name', 'due_date': 'today'})
        r = self._call_tool('lazy_rename', {'id': 1, 'description': 'new name'})
        text = r['result']['content'][0]['text']
        self.assertNotIn('Unknown tool', text)
        self.assertIn('new name', text)
        r = self._call_tool('lazy_list')
        self.assertIn('new name', r['result']['content'][0]['text'])

    def test_lazy_move_dispatched(self):
        """B1 regression: lazy_move was declared but never dispatched."""
        self._call_tool('lazy_add', {'description': 'movable', 'due_date': 'today'})
        target = (date.today() + timedelta(days=3)).isoformat()
        r = self._call_tool('lazy_move', {'id': 1, 'due_date': '+3'})
        text = r['result']['content'][0]['text']
        self.assertNotIn('Unknown tool', text)
        self.assertIn(target, text)

    def test_lazy_push(self):
        self._call_tool('lazy_add', {'description': 'shift me', 'due_date': 'today'})
        r = self._call_tool('lazy_push')
        self.assertIn('Pushed', r['result']['content'][0]['text'])

    def test_lazy_get_messages(self):
        r = self._call_tool('lazy_get_messages', {'category': 'completion'})
        text = r['result']['content'][0]['text']
        self.assertIn('completion', text)
        self.assertIn('-', text)

    def test_unknown_tool(self):
        r = self._call_tool('lazy_nonsense')
        self.assertTrue(r['result'].get('isError'))


if __name__ == "__main__":
    unittest.main()
