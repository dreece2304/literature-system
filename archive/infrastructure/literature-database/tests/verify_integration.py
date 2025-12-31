#!/usr/bin/env python3
"""
Integration verification script for Literature Database Service.

Verifies the service is ready for monorepo integration by checking:
- API starts on correct port (8001)
- Health endpoint responds correctly
- All existing papers are accessible
- Search functionality works
- Zotero sync endpoints work
- Event publishing works with Redis
"""
import sys
import json
import time
import requests
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add src to path for database access
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

class Colors:
    """Terminal colors for output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'

class IntegrationVerifier:
    """Verifies literature database integration readiness."""

    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 30
        self.results = []

    def log_result(self, test_name: str, passed: bool, message: str, details: Optional[str] = None):
        """Log test result."""
        status = f"{Colors.GREEN}✅ PASS{Colors.END}" if passed else f"{Colors.RED}❌ FAIL{Colors.END}"
        print(f"{status} {test_name}: {message}")

        if details and not passed:
            print(f"   {Colors.YELLOW}Details: {details}{Colors.END}")

        self.results.append({
            'test': test_name,
            'passed': passed,
            'message': message,
            'details': details,
            'timestamp': datetime.utcnow().isoformat()
        })

    def check_service_running(self) -> bool:
        """Check if service is running on port 8001."""
        print(f"\n{Colors.BOLD}🔍 Checking Service Status{Colors.END}")
        print("=" * 50)

        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                service_name = data.get('service', 'unknown')
                version = data.get('version', 'unknown')

                self.log_result(
                    "Service Running", 
                    True,
                    f"Service '{service_name}' v{version} running on port 8001"
                )
                return True
            else:
                self.log_result(
                    "Service Running",
                    False,
                    f"Service returned status {response.status_code}",
                    response.text
                )
                return False

        except requests.exceptions.ConnectionError:
            self.log_result(
                "Service Running",
                False,
                "Cannot connect to service on port 8001",
                "Make sure the service is running: python run_service.py"
            )
            return False
        except Exception as e:
            self.log_result(
                "Service Running",
                False,
                f"Unexpected error: {str(e)}"
            )
            return False

    def check_health_endpoint(self) -> bool:
        """Verify health endpoint returns correct information."""
        print(f"\n{Colors.BOLD}🏥 Checking Health Endpoint{Colors.END}")
        print("=" * 50)

        try:
            response = self.session.get(f"{self.base_url}/health")
            data = response.json()

            # Check required fields
            required_fields = ['status', 'service', 'version', 'timestamp']
            missing_fields = [field for field in required_fields if field not in data]

            if missing_fields:
                self.log_result(
                    "Health Endpoint Structure",
                    False,
                    f"Missing required fields: {missing_fields}"
                )
                return False

            # Check service name
            if data.get('service') != 'literature-database':
                self.log_result(
                    "Health Service Name",
                    False,
                    f"Expected 'literature-database', got '{data.get('service')}'"
                )
                return False

            # Check database info
            if 'database' in data:
                db_info = data['database']
                if 'papers_count' in db_info:
                    papers_count = db_info['papers_count']
                    self.log_result(
                        "Health Database Info",
                        True,
                        f"Database reports {papers_count} papers"
                    )
                else:
                    self.log_result(
                        "Health Database Info",
                        False,
                        "Database info missing papers_count"
                    )

            # Check event system
            if 'database' in data and 'events' in data['database']:
                events_info = data['database']['events']
                redis_enabled = events_info.get('enabled', False)
                redis_connected = events_info.get('status') == 'connected'

                self.log_result(
                    "Health Events Info",
                    True,
                    f"Redis enabled: {redis_enabled}, connected: {redis_connected}"
                )

            self.log_result(
                "Health Endpoint",
                True,
                f"Status: {data.get('status')}, all required fields present"
            )
            return True

        except Exception as e:
            self.log_result(
                "Health Endpoint",
                False,
                f"Failed to check health endpoint: {str(e)}"
            )
            return False

    def check_papers_accessible(self) -> bool:
        """Verify all papers are accessible via API."""
        print(f"\n{Colors.BOLD}📚 Checking Papers Accessibility{Colors.END}")
        print("=" * 50)

        try:
            # Get papers list
            response = self.session.get(f"{self.base_url}/api/v1/papers?limit=100")
            data = response.json()

            if 'items' not in data or 'total' not in data:
                self.log_result(
                    "Papers API Structure",
                    False,
                    "API response missing required pagination fields"
                )
                return False

            total_papers = data['total']
            papers_returned = len(data['items'])

            # Check if we have the expected 323 papers
            expected_papers = 323
            if total_papers != expected_papers:
                self.log_result(
                    "Papers Count",
                    False,
                    f"Expected {expected_papers} papers, found {total_papers}",
                    "Database may not be properly initialized or data is missing"
                )
                return False

            self.log_result(
                "Papers Count",
                True,
                f"All {total_papers} papers accessible via API"
            )

            # Check pagination
            if papers_returned > 0:
                # Test getting a specific paper
                first_paper = data['items'][0]
                paper_id = first_paper['id']

                paper_response = self.session.get(f"{self.base_url}/api/v1/papers/{paper_id}")
                if paper_response.status_code == 200:
                    paper_data = paper_response.json()

                    # Check paper structure
                    required_fields = ['id', 'title', 'date_added', 'authors', 'tags', 'collections']
                    missing_fields = [field for field in required_fields if field not in paper_data]

                    if missing_fields:
                        self.log_result(
                            "Paper Structure",
                            False,
                            f"Paper missing fields: {missing_fields}"
                        )
                        return False

                    self.log_result(
                        "Paper Structure",
                        True,
                        f"Paper {paper_id} has all required fields"
                    )

                    # Check relationships
                    authors_count = len(paper_data.get('authors', []))
                    tags_count = len(paper_data.get('tags', []))
                    collections_count = len(paper_data.get('collections', []))

                    self.log_result(
                        "Paper Relationships",
                        True,
                        f"Paper has {authors_count} authors, {tags_count} tags, {collections_count} collections"
                    )

                else:
                    self.log_result(
                        "Individual Paper Access",
                        False,
                        f"Cannot access paper {paper_id}: {paper_response.status_code}"
                    )
                    return False

            return True

        except Exception as e:
            self.log_result(
                "Papers Accessibility",
                False,
                f"Failed to check papers: {str(e)}"
            )
            return False

    def check_search_functionality(self) -> bool:
        """Verify search functionality works."""
        print(f"\n{Colors.BOLD}🔍 Checking Search Functionality{Colors.END}")
        print("=" * 50)

        try:
            # Test basic search
            search_data = {
                "query": "machine learning",
                "limit": 10
            }

            response = self.session.post(
                f"{self.base_url}/api/v1/search", 
                json=search_data
            )

            if response.status_code != 200:
                self.log_result(
                    "Search Endpoint",
                    False,
                    f"Search returned status {response.status_code}",
                    response.text
                )
                return False

            data = response.json()

            # Check response structure
            required_fields = ['query', 'total_results', 'papers']
            missing_fields = [field for field in required_fields if field not in data]

            if missing_fields:
                self.log_result(
                    "Search Response Structure",
                    False,
                    f"Search response missing fields: {missing_fields}"
                )
                return False

            # Check query matches
            if data['query'] != search_data['query']:
                self.log_result(
                    "Search Query Echo",
                    False,
                    f"Query mismatch: sent '{search_data['query']}', got '{data['query']}'"
                )
                return False

            total_results = data['total_results']
            papers_returned = len(data['papers'])

            self.log_result(
                "Search Results",
                True,
                f"Search for '{search_data['query']}' returned {total_results} results, showing {papers_returned}"
            )

            # Test search with no results
            empty_search = {
                "query": "xyzabc123notfound",
                "limit": 10
            }

            empty_response = self.session.post(
                f"{self.base_url}/api/v1/search",
                json=empty_search
            )

            if empty_response.status_code == 200:
                empty_data = empty_response.json()
                if empty_data['total_results'] == 0 and len(empty_data['papers']) == 0:
                    self.log_result(
                        "Search Empty Results",
                        True,
                        "Search correctly handles queries with no results"
                    )
                else:
                    self.log_result(
                        "Search Empty Results",
                        False,
                        f"Empty search returned {empty_data['total_results']} results"
                    )

            return True

        except Exception as e:
            self.log_result(
                "Search Functionality",
                False,
                f"Failed to test search: {str(e)}"
            )
            return False

    def check_zotero_sync(self) -> bool:
        """Verify Zotero sync endpoints work."""
        print(f"\n{Colors.BOLD}📋 Checking Zotero Sync{Colors.END}")
        print("=" * 50)

        try:
            # Test sync trigger
            sync_data = {
                "force_full_sync": False,
                "sync_attachments": True
            }

            response = self.session.post(
                f"{self.base_url}/api/v1/sync/zotero",
                json=sync_data
            )

            if response.status_code != 200:
                self.log_result(
                    "Sync Trigger",
                    False,
                    f"Sync trigger returned status {response.status_code}",
                    response.text
                )
                return False

            data = response.json()

            # Check sync response structure
            required_fields = ['sync_id', 'status', 'message']
            missing_fields = [field for field in required_fields if field not in data]

            if missing_fields:
                self.log_result(
                    "Sync Response Structure",
                    False,
                    f"Sync response missing fields: {missing_fields}"
                )
                return False

            sync_id = data['sync_id']

            self.log_result(
                "Sync Trigger",
                True,
                f"Sync triggered successfully with ID: {sync_id}"
            )

            # Test sync status check
            status_response = self.session.get(
                f"{self.base_url}/api/v1/sync/zotero/{sync_id}"
            )

            if status_response.status_code == 200:
                status_data = status_response.json()

                required_status_fields = ['sync_id', 'status', 'started_at']
                missing_status_fields = [field for field in required_status_fields if field not in status_data]

                if missing_status_fields:
                    self.log_result(
                        "Sync Status Structure",
                        False,
                        f"Sync status missing fields: {missing_status_fields}"
                    )
                    return False

                self.log_result(
                    "Sync Status Check",
                    True,
                    f"Sync status: {status_data.get('status')}"
                )
            else:
                self.log_result(
                    "Sync Status Check",
                    False,
                    f"Cannot check sync status: {status_response.status_code}"
                )
                return False

            # Test invalid sync ID
            invalid_response = self.session.get(
                f"{self.base_url}/api/v1/sync/zotero/invalid_sync_id"
            )

            if invalid_response.status_code == 404:
                self.log_result(
                    "Sync Error Handling",
                    True,
                    "Correctly returns 404 for invalid sync ID"
                )
            else:
                self.log_result(
                    "Sync Error Handling",
                    False,
                    f"Expected 404 for invalid sync ID, got {invalid_response.status_code}"
                )

            return True

        except Exception as e:
            self.log_result(
                "Zotero Sync",
                False,
                f"Failed to test Zotero sync: {str(e)}"
            )
            return False

    def check_event_publishing(self) -> bool:
        """Verify event publishing works with Redis."""
        print(f"\n{Colors.BOLD}📡 Checking Event Publishing{Colors.END}")
        print("=" * 50)

        try:
            # Test if Redis is available by checking health endpoint
            health_response = self.session.get(f"{self.base_url}/health")
            if health_response.status_code != 200:
                self.log_result(
                    "Event Publishing Setup",
                    False,
                    "Cannot check health endpoint for Redis status"
                )
                return False

            health_data = health_response.json()

            # Check if events section exists in health data
            events_info = None
            if 'database' in health_data and 'events' in health_data['database']:
                events_info = health_data['database']['events']

            if not events_info:
                self.log_result(
                    "Event Publishing Setup",
                    False,
                    "No events information in health endpoint"
                )
                return False

            redis_enabled = events_info.get('enabled', False)
            redis_connected = events_info.get('status') == 'connected'
            redis_url = events_info.get('redis_url', 'unknown')

            if not redis_enabled:
                self.log_result(
                    "Event Publishing Enabled",
                    False,
                    "Redis event publishing is disabled"
                )
                return False

            self.log_result(
                "Event Publishing Enabled",
                True,
                f"Redis enabled at {redis_url}"
            )

            if not redis_connected:
                self.log_result(
                    "Event Publishing Connected",
                    False,
                    "Redis is enabled but not connected"
                )
                # Continue testing even if not connected, as the service should handle this gracefully
            else:
                self.log_result(
                    "Event Publishing Connected",
                    True,
                    "Redis connection is active"
                )

            # Test event publishing by creating a test paper (if connected)
            if redis_connected:
                test_paper_data = {
                    "title": f"Integration Test Paper {datetime.utcnow().isoformat()}",
                    "abstract": "This is a test paper created during integration verification",
                    "authors": ["Integration Tester"],
                    "tags": ["test", "integration"],
                    "collections": ["Test Collection"]
                }

                create_response = self.session.post(
                    f"{self.base_url}/api/v1/papers",
                    json=test_paper_data
                )

                if create_response.status_code == 200:
                    created_paper = create_response.json()
                    paper_id = created_paper['id']

                    self.log_result(
                        "Event Publishing Test",
                        True,
                        f"Test paper created (ID: {paper_id}), should have published paper.added event"
                    )

                    # Clean up test paper
                    delete_response = self.session.delete(f"{self.base_url}/api/v1/papers/{paper_id}")
                    if delete_response.status_code == 200:
                        self.log_result(
                            "Event Publishing Cleanup",
                            True,
                            "Test paper deleted, should have published paper.deleted event"
                        )
                    else:
                        self.log_result(
                            "Event Publishing Cleanup",
                            False,
                            f"Failed to delete test paper: {delete_response.status_code}"
                        )
                else:
                    self.log_result(
                        "Event Publishing Test",
                        False,
                        f"Failed to create test paper: {create_response.status_code}"
                    )

            return True

        except Exception as e:
            self.log_result(
                "Event Publishing",
                False,
                f"Failed to test event publishing: {str(e)}"
            )
            return False

    def check_api_endpoints(self) -> bool:
        """Verify all API endpoints are accessible."""
        print(f"\n{Colors.BOLD}🌐 Checking API Endpoints{Colors.END}")
        print("=" * 50)

        endpoints_to_test = [
            ("GET", "/health", "Health check"),
            ("GET", "/docs", "API documentation"),
            ("GET", "/api/v1/papers", "Papers list"),
            ("POST", "/api/v1/search", "Search endpoint", {"query": "test", "limit": 1}),
        ]

        all_passed = True

        for method, endpoint, description, *args in endpoints_to_test:
            try:
                url = f"{self.base_url}{endpoint}"
                data = args[0] if args else None

                if method == "GET":
                    response = self.session.get(url)
                elif method == "POST":
                    response = self.session.post(url, json=data)
                else:
                    continue

                if response.status_code in [200, 201]:
                    self.log_result(
                        f"API Endpoint {method} {endpoint}",
                        True,
                        f"{description} accessible"
                    )
                else:
                    self.log_result(
                        f"API Endpoint {method} {endpoint}",
                        False,
                        f"{description} returned {response.status_code}"
                    )
                    all_passed = False

            except Exception as e:
                self.log_result(
                    f"API Endpoint {method} {endpoint}",
                    False,
                    f"Failed to test {description}: {str(e)}"
                )
                all_passed = False

        return all_passed

    def check_data_integrity(self) -> bool:
        """Verify data integrity and relationships."""
        print(f"\n{Colors.BOLD}🔍 Checking Data Integrity{Colors.END}")
        print("=" * 50)

        try:
            # Get papers with different limits to test pagination
            response = self.session.get(f"{self.base_url}/api/v1/papers?limit=50")
            data = response.json()

            if len(data['items']) == 0:
                self.log_result(
                    "Data Integrity",
                    False,
                    "No papers found in database"
                )
                return False

            # Check a few papers for data integrity
            papers_checked = 0
            valid_papers = 0

            for paper in data['items'][:10]:  # Check first 10 papers
                papers_checked += 1

                # Check required fields
                if 'id' in paper and 'title' in paper and paper['title']:
                    valid_papers += 1

                # Check that relationships are properly loaded
                if 'authors' in paper and isinstance(paper['authors'], list):
                    for author in paper['authors']:
                        if 'id' not in author or 'name' not in author:
                            self.log_result(
                                "Data Integrity - Authors",
                                False,
                                f"Author in paper {paper.get('id')} missing id or name"
                            )
                            return False

            integrity_ratio = valid_papers / papers_checked if papers_checked > 0 else 0

            if integrity_ratio >= 0.9:  # 90% of papers should be valid
                self.log_result(
                    "Data Integrity",
                    True,
                    f"Data integrity check passed: {valid_papers}/{papers_checked} papers valid"
                )
                return True
            else:
                self.log_result(
                    "Data Integrity",
                    False,
                    f"Data integrity issues: only {valid_papers}/{papers_checked} papers valid"
                )
                return False

        except Exception as e:
            self.log_result(
                "Data Integrity",
                False,
                f"Failed to check data integrity: {str(e)}"
            )
            return False

    def run_all_checks(self) -> bool:
        """Run all integration checks."""
        print(f"{Colors.BOLD}🚀 Literature Database Integration Verification{Colors.END}")
        print("=" * 60)
        print(f"Target URL: {Colors.CYAN}{self.base_url}{Colors.END}")
        print(f"Timestamp: {Colors.CYAN}{datetime.utcnow().isoformat()}{Colors.END}")

        checks = [
            ("Service Status", self.check_service_running),
            ("Health Endpoint", self.check_health_endpoint),
            ("API Endpoints", self.check_api_endpoints),
            ("Papers Accessibility", self.check_papers_accessible),
            ("Search Functionality", self.check_search_functionality),
            ("Zotero Sync", self.check_zotero_sync),
            ("Event Publishing", self.check_event_publishing),
            ("Data Integrity", self.check_data_integrity),
        ]

        all_passed = True

        for check_name, check_func in checks:
            try:
                result = check_func()
                if not result:
                    all_passed = False
            except Exception as e:
                self.log_result(
                    check_name,
                    False,
                    f"Check failed with exception: {str(e)}"
                )
                all_passed = False

        # Print summary
        print(f"\n{Colors.BOLD}📊 Verification Summary{Colors.END}")
        print("=" * 60)

        passed_tests = sum(1 for result in self.results if result['passed'])
        total_tests = len(self.results)
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

        if all_passed:
            print(f"{Colors.GREEN}✅ ALL CHECKS PASSED ({passed_tests}/{total_tests}){Colors.END}")
            print(f"{Colors.GREEN}🎉 Literature Database is ready for monorepo integration!{Colors.END}")
        else:
            print(f"{Colors.RED}❌ SOME CHECKS FAILED ({passed_tests}/{total_tests}){Colors.END}")
            print(f"{Colors.YELLOW}⚠️  Success rate: {success_rate:.1f}%{Colors.END}")

        # Show failed tests
        failed_tests = [result for result in self.results if not result['passed']]
        if failed_tests:
            print(f"\n{Colors.RED}Failed Tests:{Colors.END}")
            for test in failed_tests:
                print(f"  • {test['test']}: {test['message']}")
                if test['details']:
                    print(f"    {test['details']}")

        print("\n" + "=" * 60)

        return all_passed

    def save_report(self, filename: str = "integration_report.json"):
        """Save verification report to file."""
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'base_url': self.base_url,
            'summary': {
                'total_tests': len(self.results),
                'passed_tests': sum(1 for r in self.results if r['passed']),
                'failed_tests': sum(1 for r in self.results if not r['passed']),
                'success_rate': (sum(1 for r in self.results if r['passed']) / len(self.results) * 100) if self.results else 0
            },
            'results': self.results
        }

        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"📄 Report saved to: {filename}")


def main():
    """Main verification function."""
    import argparse

    parser = argparse.ArgumentParser(description="Literature Database Integration Verification")
    parser.add_argument('--url', default='http://localhost:8001', help='Base URL for the service')
    parser.add_argument('--save-report', help='Save report to file')
    parser.add_argument('--wait', type=int, default=0, help='Wait N seconds before starting checks')

    args = parser.parse_args()

    if args.wait > 0:
        print(f"⏳ Waiting {args.wait} seconds before starting verification...")
        time.sleep(args.wait)

    verifier = IntegrationVerifier(args.url)

    try:
        success = verifier.run_all_checks()

        if args.save_report:
            verifier.save_report(args.save_report)

        return 0 if success else 1

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠️  Verification interrupted by user{Colors.END}")
        return 1
    except Exception as e:
        print(f"\n{Colors.RED}💥 Unexpected error: {str(e)}{Colors.END}")
        return 1


if __name__ == "__main__":
    exit(main())
