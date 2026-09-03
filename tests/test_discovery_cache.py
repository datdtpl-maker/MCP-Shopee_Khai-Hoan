import asyncio
import unittest

from shopee_sync.src.discovery_cache import DiscoveryCache


class DiscoveryCacheTest(unittest.TestCase):
    def test_hit_avoids_loader_until_ttl(self):
        now = [100.0]
        calls = []
        cache = DiscoveryCache(10, clock=lambda: now[0])

        async def loader():
            calls.append(1)
            return ["tool"]

        async def run():
            self.assertEqual(await cache.get(loader), ["tool"])
            self.assertEqual(await cache.get(loader), ["tool"])
            now[0] = 111
            self.assertEqual(await cache.get(loader), ["tool"])

        asyncio.run(run())
        self.assertEqual(len(calls), 2)

    def test_invalidation_forces_reload(self):
        calls = []
        cache = DiscoveryCache(60)

        async def loader():
            calls.append(1)
            return calls[:]

        async def run():
            self.assertEqual(await cache.get(loader), [1])
            cache.invalidate()
            self.assertEqual(await cache.get(loader), [1, 1])

        asyncio.run(run())
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
