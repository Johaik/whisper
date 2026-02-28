import time
import random
import string

class MockGoogleContactsService_Original:
    def __init__(self):
        self._contacts_cache = {}

    def lookup_contact_name(self, phone_number):
        normalized = phone_number
        if normalized in self._contacts_cache:
            return self._contacts_cache[normalized]

        for length in [8, 7, 6]:
            if len(normalized) >= length:
                short = normalized[-length:]
                for cached_phone, name in self._contacts_cache.items():
                    if cached_phone.endswith(short):
                        return name
        return None

class MockGoogleContactsService_Optimized:
    def __init__(self):
        self._contacts_cache = {}
        self._suffix_cache = {}

    def build_cache(self):
        for phone, name in self._contacts_cache.items():
            for length in [8, 7, 6]:
                if len(phone) >= length:
                    self._suffix_cache[phone[-length:]] = name

    def lookup_contact_name(self, phone_number):
        normalized = phone_number
        if normalized in self._contacts_cache:
            return self._contacts_cache[normalized]

        for length in [8, 7, 6]:
            if len(normalized) >= length:
                short = normalized[-length:]
                if short in self._suffix_cache:
                    return self._suffix_cache[short]
        return None

def run_benchmark():
    num_contacts = 5000
    queries = 1000

    orig_service = MockGoogleContactsService_Original()
    opt_service = MockGoogleContactsService_Optimized()

    # Populate caches
    for i in range(num_contacts):
        phone = f"155512{i:04d}"
        name = f"Contact {i}"
        orig_service._contacts_cache[phone] = name
        opt_service._contacts_cache[phone] = name

    opt_service.build_cache()

    # Generate test queries
    test_queries = []
    for i in range(queries):
        # some exact, some suffix, some misses
        if i % 3 == 0:
            test_queries.append(f"155512{i:04d}") # exact match
        elif i % 3 == 1:
            test_queries.append(f"955512{i:04d}") # suffix match
        else:
            test_queries.append(f"999999{i:04d}") # miss

    start_orig = time.time()
    for q in test_queries:
        orig_service.lookup_contact_name(q)
    end_orig = time.time()

    start_opt = time.time()
    for q in test_queries:
        opt_service.lookup_contact_name(q)
    end_opt = time.time()

    print(f"Original time : {end_orig - start_orig:.5f}s")
    print(f"Optimized time: {end_opt - start_opt:.5f}s")
    print(f"Speedup: {(end_orig - start_orig) / (end_opt - start_opt):.2f}x")

if __name__ == "__main__":
    run_benchmark()
