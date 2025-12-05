 SQL Proxy - MySQL Protocol Server (SQLite Backend)
=====================================================

This project provides a custom implementation of the MySQL wire protocol server, utilizing an SQLite backend for storage. It's designed to serve as a standalone replacement for traditional MySQL servers in development environments or applications where lightweight and simplicity are important.

Key Features
------------

- Utilizes SQLite as the underlying database engine, ensuring minimal system resources usage.
- Supports MySQL wire protocol version 10 for compatibility with various client libraries.
- Implements key MySQL capabilities like authentication, query handling, and result streaming.
- Can be easily extended to support additional features or custom SQLite extensions.

Installation
------------

The easiest way to get started is by cloning the repository and creating a virtual environment using Python 3.x:

```sh
$ git clone https://github.com/yourusername/sql_proxy.git
$ cd sql_proxy
$ python -m venv venv
$ source venv/bin/activate
$ pip install -r requirements.txt
```

Configuration
-------------

To configure the server, create a `.env` file in the project root directory and set the desired options:

- OLLAMA_API_URL: The API URL for an optional Language Model API (e.g., Mistral)
- OLLAMA_MODEL: The model to use if an API is available
- MYSQL_PORT: The port number the server will listen on (default 3307)

You can create a sample configuration file by copying `.env.example` to `.env`.

Database Schema Definition
---------------------------

The database schema is defined in JSON format using the `config.py` file. To add or modify tables, simply update the JSON structure within this file. Keep in mind that SQLite does not support user-defined functions or stored procedures like MySQL, so be aware of any limitations when designing your database.

Data Population
---------------

To populate the database with sample data, run `python generate_data.py` from the project root directory. You can specify a custom database path using the `--db-path` option if needed. By default, the server will initialize an empty database upon startup (if it does not exist).

Running the Server
-------------------

To start the server, simply execute:

```sh
$ python server.py
```

The server will output its configuration and status, as well as log incoming client connections. To connect to the server using a MySQL client, use the following command:

```sh
$ mysql -h localhost -P <MYSQL_PORT> -u root
```

Note that the `root` user is automatically created during database initialization with no password set by default. If you need to secure access, we recommend setting a password and updating any necessary configurations in your MySQL client.

Contributing
------------

We welcome contributions from the community! To get started, please fork the repository and submit pull requests for new features or bug fixes. Before making changes, be sure to read our [contributing guidelines](CONTRIBUTING.md).

License
-------

This project is licensed under the MIT License - see the `LICENSE` file for details.