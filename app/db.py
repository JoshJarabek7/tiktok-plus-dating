from os import environ

from meta import SingletonMeta
from neo4j import Driver, GraphDatabase


class DatabaseManager(metaclass=SingletonMeta):
    """Singleton manager for Neo4j database connections.

    This class manages the lifecycle of Neo4j database connections, ensuring
    only one connection is active at a time and handling connection pooling.

    Attributes:
        _driver: The Neo4j driver instance
        _uri: URI of the Neo4j database
        _auth: Tuple of username and password for authentication
        _database: Name of the Neo4j database to connect to
    """

    def __init__(self) -> None:
        """Initialize the database manager.

        Sets up connection parameters and verifies connectivity.

        Raises:
            neo4j.exceptions.ServiceUnavailable: If database is not reachable
            neo4j.exceptions.AuthError: If credentials are invalid
        """
        self._driver: Driver | None = None
        self._uri: str = environ.get("NEO4J_URI", "")
        self._auth: tuple[str, str] = (
            environ.get("NEO4J_USER", ""),
            environ.get("NEO4J_PASSWORD", ""),
        )
        self._database: str = environ.get("NEO4J_DATABASE", "")
        # Verify connectivity during initialization
        self._verify_connectivity()

    def _verify_connectivity(self) -> None:
        """Verify database connectivity with current credentials.

        Tests the connection to the database using the configured credentials.
        This is called during initialization to ensure the database is accessible.

        Raises:
            neo4j.exceptions.ServiceUnavailable: If database is not reachable
            neo4j.exceptions.AuthError: If credentials are invalid
        """
        with GraphDatabase.driver(self._uri, auth=self._auth) as test_driver:
            test_driver.verify_connectivity()

    @property
    def driver(self) -> Driver:
        """Get or create the Neo4j driver instance.

        If no driver exists, creates a new one using the configured credentials.
        Otherwise returns the existing driver instance.

        Returns:
            The Neo4j driver instance that can be used for database operations
        """
        if not self._driver:
            self._driver = GraphDatabase.driver(
                self._uri,
                auth=self._auth,
                max_connection_pool_size=10,  # Default is 100
                connection_timeout=30,  # Seconds
            )
        return self._driver

    @property
    def database(self) -> str:
        """Get the name of the Neo4j database.

        Returns:
            The configured database name to use for operations
        """
        return self._database

    def close(self) -> None:
        """Close the database connection.

        This method should be called when shutting down the application
        to properly close the database connection and clean up resources.
        If no connection exists, this is a no-op.
        """
        if self._driver:
            self._driver.close()
            self._driver = None
