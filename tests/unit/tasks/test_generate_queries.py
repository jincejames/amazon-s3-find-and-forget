import os
from types import SimpleNamespace

import mock
import pytest
from mock import patch

with patch.dict(os.environ, {"QueryQueue": "test"}):
    from backend.lambdas.tasks.generate_queries import (
        handler,
        get_table,
        get_partitions,
        cast_to_type,
        get_deletion_queue,
        generate_athena_queries,
        get_data_mappers,
        get_inner_children,
        get_nested_children,
    )

pytestmark = [pytest.mark.unit, pytest.mark.task]


@patch("backend.lambdas.tasks.generate_queries.batch_sqs_msgs")
@patch("backend.lambdas.tasks.generate_queries.get_deletion_queue")
@patch("backend.lambdas.tasks.generate_queries.get_data_mappers")
@patch("backend.lambdas.tasks.generate_queries.generate_athena_queries")
def test_it_invokes_athena_query_generator(
    gen_athena_queries, get_data_mappers, get_del_q, batch_sqs_msgs_mock
):
    get_del_q.return_value = [{"MatchId": "hi"}]
    queries = [
        {
            "DataMapperId": "a",
            "QueryExecutor": "athena",
            "Format": "parquet",
            "Database": "test_db",
            "Table": "test_table",
            "Columns": [{"Column": "customer_id", "MatchIds": ["hi"]}],
            "PartitionKeys": [{"Key": "product_category", "Value": "Books"}],
            "DeleteOldVersions": True,
        }
    ]
    gen_athena_queries.return_value = queries
    get_data_mappers.return_value = iter(
        [
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Columns": ["customer_id"],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
            }
        ]
    )
    handler({"ExecutionName": "test"}, SimpleNamespace())
    batch_sqs_msgs_mock.assert_called_with(mock.ANY, queries)


@patch("backend.lambdas.tasks.generate_queries.batch_sqs_msgs")
@patch("backend.lambdas.tasks.generate_queries.get_deletion_queue")
@patch("backend.lambdas.tasks.generate_queries.get_data_mappers")
def test_it_raises_for_unknown_query_executor(
    get_data_mappers, get_del_q, batch_sqs_msgs_mock
):
    get_del_q.return_value = [{"MatchId": "hi"}]
    get_data_mappers.return_value = iter(
        [
            {
                "DataMapperId": "a",
                "QueryExecutor": "invalid",
                "Columns": ["customer_id"],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
            }
        ]
    )
    with pytest.raises(NotImplementedError):
        handler({"ExecutionName": "test"}, SimpleNamespace())
        batch_sqs_msgs_mock.assert_not_called()


class TestAthenaQueries:
    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_handles_single_columns(self, get_partitions_mock, get_table_mock):
        columns = [{"Name": "customer_id"}]
        partition_keys = ["product_category"]
        partitions = [["Books"]]
        get_table_mock.return_value = table_stub(columns, partition_keys)
        get_partitions_mock.return_value = [
            partition_stub(p, columns) for p in partitions
        ]
        resp = generate_athena_queries(
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
            },
            [{"MatchId": "hi"}],
        )
        assert resp == [
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Database": "test_db",
                "Table": "test_table",
                "Columns": [
                    {"Column": "customer_id", "MatchIds": ["hi"], "Type": "Simple"}
                ],
                "PartitionKeys": [{"Key": "product_category", "Value": "Books"}],
                "DeleteOldVersions": True,
            }
        ]

    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_handles_int_matches(self, get_partitions_mock, get_table_mock):
        columns = [{"Name": "customer_id"}]
        partition_keys = ["product_category"]
        partitions = [["Books"]]
        get_table_mock.return_value = table_stub(columns, partition_keys)
        get_partitions_mock.return_value = [
            partition_stub(p, columns) for p in partitions
        ]
        resp = generate_athena_queries(
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
            },
            [{"MatchId": 12345}, {"MatchId": 23456}],
        )
        assert resp == [
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Database": "test_db",
                "Table": "test_table",
                "Columns": [
                    {
                        "Column": "customer_id",
                        "MatchIds": ["12345", "23456"],
                        "Type": "Simple",
                    }
                ],
                "PartitionKeys": [{"Key": "product_category", "Value": "Books"}],
                "DeleteOldVersions": True,
            }
        ]

    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_handles_int_partitions(self, get_partitions_mock, get_table_mock):
        columns = [{"Name": "customer_id"}]
        partition_keys = ["year"]
        partitions = [["2010"]]
        get_table_mock.return_value = table_stub(
            columns, partition_keys, partition_keys_type="int"
        )
        get_partitions_mock.return_value = [
            partition_stub(p, columns) for p in partitions
        ]
        resp = generate_athena_queries(
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
            },
            [{"MatchId": "hi"}],
        )
        assert resp == [
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Database": "test_db",
                "Table": "test_table",
                "Columns": [
                    {"Column": "customer_id", "MatchIds": ["hi"], "Type": "Simple"}
                ],
                "PartitionKeys": [{"Key": "year", "Value": 2010}],
                "DeleteOldVersions": True,
            }
        ]

    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_handles_multiple_columns(self, get_partitions_mock, get_table_mock):
        columns = [{"Name": "customer_id"}, {"Name": "alt_customer_id"}]
        partition_keys = ["product_category"]
        partitions = [["Books"]]
        get_table_mock.return_value = table_stub(columns, partition_keys)
        get_partitions_mock.return_value = [
            partition_stub(p, columns) for p in partitions
        ]
        resp = generate_athena_queries(
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
            },
            [{"MatchId": "hi"}],
        )

        assert resp == [
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Database": "test_db",
                "Table": "test_table",
                "Columns": [
                    {"Column": "customer_id", "MatchIds": ["hi"], "Type": "Simple"},
                    {"Column": "alt_customer_id", "MatchIds": ["hi"], "Type": "Simple"},
                ],
                "PartitionKeys": [{"Key": "product_category", "Value": "Books"}],
                "DeleteOldVersions": True,
            }
        ]

    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_handles_composite_columns(self, get_partitions_mock, get_table_mock):
        columns = [
            {"Name": "first_name"},
            {"Name": "last_name"},
        ]
        partition_keys = ["product_category"]
        partitions = [["Books"]]
        get_table_mock.return_value = table_stub(columns, partition_keys)
        get_partitions_mock.return_value = [
            partition_stub(p, columns) for p in partitions
        ]
        resp = generate_athena_queries(
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
            },
            [
                {
                    "MatchId": [
                        {"Column": "first_name", "Value": "John"},
                        {"Column": "last_name", "Value": "Doe"},
                    ],
                    "Type": "Composite",
                    "DataMappers": ["a"],
                }
            ],
        )

        assert resp == [
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Database": "test_db",
                "Table": "test_table",
                "Columns": [
                    {
                        "Columns": ["first_name", "last_name"],
                        "MatchIds": [["John", "Doe"]],
                        "Type": "Composite",
                    }
                ],
                "PartitionKeys": [{"Key": "product_category", "Value": "Books"}],
                "DeleteOldVersions": True,
            }
        ]

    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_handles_mixed_columns(self, get_partitions_mock, get_table_mock):
        columns = [
            {"Name": "customer_id"},
            {"Name": "first_name"},
            {"Name": "last_name"},
            {"Name": "age", "Type": "int"},
        ]
        partition_keys = ["product_category"]
        partitions = [["Books"]]
        get_table_mock.return_value = table_stub(columns, partition_keys)
        get_partitions_mock.return_value = [
            partition_stub(p, columns) for p in partitions
        ]
        resp = generate_athena_queries(
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
            },
            [
                {"MatchId": "12345", "Type": "Simple"},
                {"MatchId": "23456", "Type": "Simple"},
                {"MatchId": "23456", "Type": "Simple"},  # duplicate
                {
                    "MatchId": [
                        {"Column": "first_name", "Value": "John"},
                        {"Column": "last_name", "Value": "Doe"},
                    ],
                    "Type": "Composite",
                    "DataMappers": ["a"],
                },
                {
                    "MatchId": [
                        {"Column": "first_name", "Value": "Jane"},
                        {"Column": "last_name", "Value": "Doe"},
                    ],
                    "Type": "Composite",
                    "DataMappers": ["a"],
                },
                {  # duplicate
                    "MatchId": [
                        {"Column": "first_name", "Value": "Jane"},
                        {"Column": "last_name", "Value": "Doe"},
                    ],
                    "Type": "Composite",
                    "DataMappers": ["a"],
                },
                {
                    "MatchId": [
                        {"Column": "last_name", "Value": "Smith"},
                        {"Column": "age", "Value": "28"},
                    ],
                    "Type": "Composite",
                    "DataMappers": ["a"],
                },
            ],
        )

        assert resp == [
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Database": "test_db",
                "Table": "test_table",
                "Columns": [
                    {
                        "Column": "customer_id",
                        "MatchIds": ["12345", "23456"],
                        "Type": "Simple",
                    },
                    {
                        "Column": "first_name",
                        "MatchIds": ["12345", "23456"],
                        "Type": "Simple",
                    },
                    {
                        "Column": "last_name",
                        "MatchIds": ["12345", "23456"],
                        "Type": "Simple",
                    },
                    {"Column": "age", "MatchIds": [12345, 23456], "Type": "Simple"},
                    {
                        "Columns": ["first_name", "last_name"],
                        "MatchIds": [["John", "Doe"], ["Jane", "Doe"]],
                        "Type": "Composite",
                    },
                    {
                        "Columns": ["age", "last_name"],
                        "MatchIds": [[28, "Smith"]],
                        "Type": "Composite",
                    },
                ],
                "PartitionKeys": [{"Key": "product_category", "Value": "Books"}],
                "DeleteOldVersions": True,
            }
        ]

    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_handles_multiple_partition_keys(
        self, get_partitions_mock, get_table_mock
    ):
        columns = [{"Name": "customer_id"}]
        partition_keys = ["year", "month"]
        partitions = [["2019", "01"]]
        get_table_mock.return_value = table_stub(columns, partition_keys)
        get_partitions_mock.return_value = [
            partition_stub(p, columns) for p in partitions
        ]

        resp = generate_athena_queries(
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
            },
            [{"MatchId": "hi"}],
        )

        assert resp == [
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Database": "test_db",
                "Table": "test_table",
                "Columns": [
                    {"Column": "customer_id", "MatchIds": ["hi"], "Type": "Simple"}
                ],
                "PartitionKeys": [
                    {"Key": "year", "Value": "2019"},
                    {"Key": "month", "Value": "01"},
                ],
                "DeleteOldVersions": True,
            }
        ]

    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_handles_multiple_partition_values(
        self, get_partitions_mock, get_table_mock
    ):
        columns = [{"Name": "customer_id"}]
        partition_keys = ["year", "month"]
        partitions = [["2018", "12"], ["2019", "01"], ["2019", "02"]]
        get_table_mock.return_value = table_stub(columns, partition_keys)
        get_partitions_mock.return_value = [
            partition_stub(p, columns) for p in partitions
        ]

        resp = generate_athena_queries(
            {
                "DataMapperId": "a",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutor": "athena",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
            },
            [{"MatchId": "hi"}],
        )

        assert resp == [
            {
                "DataMapperId": "a",
                "Database": "test_db",
                "Table": "test_table",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Columns": [
                    {"Column": "customer_id", "MatchIds": ["hi"], "Type": "Simple"}
                ],
                "PartitionKeys": [
                    {"Key": "year", "Value": "2018"},
                    {"Key": "month", "Value": "12"},
                ],
                "DeleteOldVersions": True,
            },
            {
                "DataMapperId": "a",
                "Database": "test_db",
                "Table": "test_table",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Columns": [
                    {"Column": "customer_id", "MatchIds": ["hi"], "Type": "Simple"}
                ],
                "PartitionKeys": [
                    {"Key": "year", "Value": "2019"},
                    {"Key": "month", "Value": "01"},
                ],
                "DeleteOldVersions": True,
            },
            {
                "DataMapperId": "a",
                "Database": "test_db",
                "Table": "test_table",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Columns": [
                    {"Column": "customer_id", "MatchIds": ["hi"], "Type": "Simple"}
                ],
                "PartitionKeys": [
                    {"Key": "year", "Value": "2019"},
                    {"Key": "month", "Value": "02"},
                ],
                "DeleteOldVersions": True,
            },
        ]

    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_propagates_optional_properties(
        self, get_partitions_mock, get_table_mock
    ):
        columns = [{"Name": "customer_id"}]
        partition_keys = ["year", "month"]
        partitions = [["2018", "12"], ["2019", "01"]]
        get_table_mock.return_value = table_stub(columns, partition_keys)
        get_partitions_mock.return_value = [
            partition_stub(p, columns) for p in partitions
        ]

        resp = generate_athena_queries(
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
                "RoleArn": "arn:aws:iam::accountid:role/rolename",
                "DeleteOldVersions": True,
            },
            [{"MatchId": "hi"}],
        )

        assert resp == [
            {
                "DataMapperId": "a",
                "Database": "test_db",
                "Table": "test_table",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Columns": [
                    {"Column": "customer_id", "MatchIds": ["hi"], "Type": "Simple"}
                ],
                "PartitionKeys": [
                    {"Key": "year", "Value": "2018"},
                    {"Key": "month", "Value": "12"},
                ],
                "RoleArn": "arn:aws:iam::accountid:role/rolename",
                "DeleteOldVersions": True,
            },
            {
                "DataMapperId": "a",
                "Database": "test_db",
                "Table": "test_table",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Columns": [
                    {"Column": "customer_id", "MatchIds": ["hi"], "Type": "Simple"}
                ],
                "PartitionKeys": [
                    {"Key": "year", "Value": "2019"},
                    {"Key": "month", "Value": "01"},
                ],
                "RoleArn": "arn:aws:iam::accountid:role/rolename",
                "DeleteOldVersions": True,
            },
        ]

    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_filters_users_from_non_applicable_tables(
        self, get_partitions_mock, get_table_mock
    ):
        columns = [{"Name": "customer_id"}]
        partition_keys = ["product_category"]
        partitions = [["Books"]]
        get_table_mock.return_value = table_stub(columns, partition_keys)
        get_partitions_mock.return_value = [
            partition_stub(p, columns) for p in partitions
        ]
        resp = generate_athena_queries(
            {
                "DataMapperId": "B",
                "QueryExecutor": "athena",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "B",
                },
            },
            [
                {"MatchId": "123", "DataMappers": ["A"]},
                {"MatchId": "456", "DataMappers": []},
            ],
        )

        assert resp == [
            {
                "DataMapperId": "B",
                "Database": "test_db",
                "Table": "B",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Columns": [
                    {"Column": "customer_id", "MatchIds": ["456"], "Type": "Simple"}
                ],
                "PartitionKeys": [{"Key": "product_category", "Value": "Books"}],
                "DeleteOldVersions": True,
            }
        ]

    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_handles_unpartitioned_data(self, get_partitions_mock, get_table_mock):
        columns = [{"Name": "customer_id"}]
        get_table_mock.return_value = table_stub(columns, [])
        get_partitions_mock.return_value = []
        resp = generate_athena_queries(
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
            },
            [{"MatchId": "hi"}],
        )
        assert resp == [
            {
                "DataMapperId": "a",
                "Database": "test_db",
                "Table": "test_table",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Columns": [
                    {"Column": "customer_id", "MatchIds": ["hi"], "Type": "Simple"}
                ],
                "PartitionKeys": [],
                "DeleteOldVersions": True,
            }
        ]

    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_propagates_role_arn_for_unpartitioned_data(
        self, get_partitions_mock, get_table_mock
    ):
        columns = [{"Name": "customer_id"}]
        get_table_mock.return_value = table_stub(columns, [])
        get_partitions_mock.return_value = []
        resp = generate_athena_queries(
            {
                "DataMapperId": "a",
                "QueryExecutor": "athena",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
                "RoleArn": "arn:aws:iam::accountid:role/rolename",
            },
            [{"MatchId": "hi"}],
        )
        assert resp == [
            {
                "DataMapperId": "a",
                "Database": "test_db",
                "Table": "test_table",
                "QueryExecutor": "athena",
                "Format": "parquet",
                "Columns": [
                    {"Column": "customer_id", "MatchIds": ["hi"], "Type": "Simple"}
                ],
                "PartitionKeys": [],
                "RoleArn": "arn:aws:iam::accountid:role/rolename",
                "DeleteOldVersions": True,
            }
        ]

    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_removes_queries_with_no_applicable_matches(
        self, get_partitions_mock, get_table_mock
    ):
        columns = [{"Name": "customer_id"}]
        get_table_mock.return_value = table_stub(columns, [])
        get_partitions_mock.return_value = []
        resp = generate_athena_queries(
            {
                "DataMapperId": "A",
                "QueryExecutor": "athena",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
            },
            [{"MatchId": "123", "DataMappers": ["B"]}],
        )
        assert resp == []

    @patch("backend.lambdas.tasks.generate_queries.get_table")
    @patch("backend.lambdas.tasks.generate_queries.get_partitions")
    def test_it_removes_queries_with_no_applicable_matches_for_partitioned_data(
        self, get_partitions_mock, get_table_mock
    ):
        columns = [{"Name": "customer_id"}]
        partition_keys = ["product_category"]
        partitions = [["Books"], ["Beauty"]]
        get_table_mock.return_value = table_stub(columns, partition_keys)
        get_partitions_mock.return_value = [
            partition_stub(p, columns) for p in partitions
        ]
        resp = generate_athena_queries(
            {
                "DataMapperId": "A",
                "QueryExecutor": "athena",
                "Columns": [col["Name"] for col in columns],
                "Format": "parquet",
                "QueryExecutorParameters": {
                    "DataCatalogProvider": "glue",
                    "Database": "test_db",
                    "Table": "test_table",
                },
            },
            [{"MatchId": "123", "DataMappers": ["C"]}],
        )
        assert resp == []

    @patch("backend.lambdas.tasks.generate_queries.glue_client")
    def test_it_returns_table(self, client):
        client.get_table.return_value = {"Table": {"Name": "test"}}
        result = get_table("test_db", "test_table")
        assert {"Name": "test"} == result
        client.get_table.assert_called_with(DatabaseName="test_db", Name="test_table")

    @patch("backend.lambdas.tasks.generate_queries.paginate")
    def test_it_returns_all_partitions(self, paginate):
        paginate.return_value = iter(["blah"])
        result = list(get_partitions("test_db", "test_table"))
        assert ["blah"] == result
        paginate.assert_called_with(
            mock.ANY,
            mock.ANY,
            ["Partitions"],
            **{"DatabaseName": "test_db", "TableName": "test_table"}
        )

    def test_it_converts_supported_types(self):
        for scenario in [
            {"value": "m", "type": "char", "expected": "m"},
            {"value": "mystr", "type": "string", "expected": "mystr"},
            {"value": "mystr", "type": "varchar", "expected": "mystr"},
            {"value": "2", "type": "bigint", "expected": 2},
            {"value": "2", "type": "int", "expected": 2},
            {"value": "2", "type": "smallint", "expected": 2},
            {"value": "2", "type": "tinyint", "expected": 2},
            {"value": "2.23", "type": "double", "expected": 2.23},
            {"value": "2.23", "type": "float", "expected": 2.23},
        ]:
            res = cast_to_type(
                scenario["value"],
                "test_col",
                {
                    "StorageDescriptor": {
                        "Columns": [{"Name": "test_col", "Type": scenario["type"]}]
                    }
                },
            )

            assert res == scenario["expected"]

    def test_it_converts_supported_types_when_nested_in_struct(self):
        column_type = "struct<type:int,x:map<string,struct<a:int>>,info:struct<user_id:int,name:string>>"
        table = {
            "StorageDescriptor": {"Columns": [{"Name": "user", "Type": column_type}]}
        }
        for scenario in [
            {"value": "john_doe", "id": "user.info.name", "expected": "john_doe"},
            {"value": "1234567890", "id": "user.info.user_id", "expected": 1234567890},
            {"value": "1", "id": "user.type", "expected": 1},
        ]:
            res = cast_to_type(scenario["value"], scenario["id"], table)
            assert res == scenario["expected"]

    def test_it_throws_for_unknown_col(self):
        with pytest.raises(ValueError):
            cast_to_type(
                "mystr",
                "doesnt_exist",
                {
                    "StorageDescriptor": {
                        "Columns": [{"Name": "test_col", "Type": "string"}]
                    }
                },
            )

    def test_it_throws_for_unsupported_complex_nested_types(self):
        for scenario in [
            "array<x:int>",
            "array<struct<x:int>>",
            "struct<a:array<struct<a:int,x:int>>>",
            "array<struct<a:int,b:struct<x:int>>>",
            "struct<a:map<string,struct<x:int>>>",
            "map<string,struct<x:int>>",
        ]:
            with pytest.raises(ValueError):
                cast_to_type(
                    123,
                    "user.x",
                    {
                        "StorageDescriptor": {
                            "Columns": [{"Name": "user", "Type": scenario}]
                        }
                    },
                )

    def test_it_throws_for_unsupported_col_types(self):
        with pytest.raises(ValueError) as e:
            cast_to_type(
                "2.56",
                "test_col",
                {
                    "StorageDescriptor": {
                        "Columns": [{"Name": "test_col", "Type": "decimal"}]
                    }
                },
            )
        assert (
            e.value.args[0]
            == "Column test_col is not a supported column type for querying"
        )

    def test_it_throws_for_unconvertable_matches(self):
        with pytest.raises(ValueError):
            cast_to_type(
                "mystr",
                "test_col",
                {
                    "StorageDescriptor": {
                        "Columns": [{"Name": "test_col", "Type": "int"}]
                    }
                },
            )

    def test_it_throws_for_invalid_schema_for_inner_children(self):
        with pytest.raises(ValueError) as e:
            get_inner_children("struct<name:string", "struct<", ">")
        assert e.value.args[0] == "Column schema is not valid"

    def test_it_throws_for_invalid_schema_for_nested_children(self):
        with pytest.raises(ValueError) as e:
            get_nested_children(
                "struct<name:string,age:int,s:struct<n:int>,b:string", "struct"
            )
        assert e.value.args[0] == "Column schema is not valid"


@patch("backend.lambdas.tasks.generate_queries.jobs_table")
def test_it_fetches_deletion_queue_from_ddb(table_mock):
    table_mock.get_item.return_value = {
        "Item": {"DeletionQueueItems": [{"DataMappers": [], "MatchId": "123"}]}
    }

    resp = get_deletion_queue("job123")
    assert resp == [{"DataMappers": [], "MatchId": "123"}]
    table_mock.get_item.assert_called_with(Key={"Id": "job123", "Sk": "job123"})


@patch("backend.lambdas.tasks.generate_queries.deserialize_item")
@patch("backend.lambdas.tasks.generate_queries.paginate")
def test_it_fetches_deserialized_data_mappers(paginate_mock, deserialize_mock):
    dm = {
        "DataMapperId": "a",
        "QueryExecutor": "athena",
        "Columns": ["customer_id"],
        "Format": "parquet",
        "QueryExecutorParameters": {
            "DataCatalogProvider": "glue",
            "Database": "test_db",
            "Table": "test_table",
        },
    }
    deserialize_mock.return_value = dm
    paginate_mock.return_value = iter([dm])

    resp = get_data_mappers()
    assert list(resp) == [dm]


def partition_stub(values, columns, table_name="test_table"):
    return {
        "Values": values,
        "DatabaseName": "test",
        "TableName": table_name,
        "CreationTime": 1572440736.0,
        "LastAccessTime": 0.0,
        "StorageDescriptor": {
            "Columns": [
                {"Name": col["Name"], "Type": col.get("Type", "string")}
                for col in columns
            ],
            "Location": "s3://bucket/location",
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "Compressed": False,
            "NumberOfBuckets": -1,
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                "Parameters": {"serialization.format": "1"},
            },
            "BucketColumns": [],
            "SortColumns": [],
            "Parameters": {},
            "SkewedInfo": {
                "SkewedColumnNames": [],
                "SkewedColumnValues": [],
                "SkewedColumnValueLocationMaps": {},
            },
            "StoredAsSubDirectories": False,
        },
    }


def table_stub(
    columns, partition_keys, table_name="test_table", partition_keys_type="string"
):
    return {
        "Name": table_name,
        "DatabaseName": "test",
        "Owner": "test",
        "CreateTime": 1572438253.0,
        "UpdateTime": 1572438253.0,
        "LastAccessTime": 0.0,
        "Retention": 0,
        "StorageDescriptor": {
            "Columns": [
                {"Name": col["Name"], "Type": col.get("Type", "string")}
                for col in columns
            ],
            "Location": "s3://bucket/location",
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "Compressed": False,
            "NumberOfBuckets": -1,
            "SerdeInfo": {
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                "Parameters": {"serialization.format": "1"},
            },
            "BucketColumns": [],
            "SortColumns": [],
            "Parameters": {},
            "SkewedInfo": {
                "SkewedColumnNames": [],
                "SkewedColumnValues": [],
                "SkewedColumnValueLocationMaps": {},
            },
            "StoredAsSubDirectories": False,
        },
        "PartitionKeys": [
            {"Name": partition_key, "Type": partition_keys_type}
            for partition_key in partition_keys
        ],
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {"EXTERNAL": "TRUE",},
    }
