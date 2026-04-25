import unittest

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

from core.models.article import Article


class TestArticleMySQLSchema(unittest.TestCase):
    def test_publish_status_is_mysql_indexable(self):
        table_sql = str(CreateTable(Article.__table__).compile(dialect=mysql.dialect()))

        self.assertIn("publish_status VARCHAR(", table_sql)
        self.assertNotIn("publish_status TEXT", table_sql)
        self.assertNotIn("publish_status MEDIUMTEXT", table_sql)

        publish_status_indexes = [
            index for index in Article.__table__.indexes if index.name == "ix_articles_publish_status"
        ]
        self.assertEqual(len(publish_status_indexes), 1)

        index_sql = str(CreateIndex(publish_status_indexes[0]).compile(dialect=mysql.dialect()))
        self.assertIn("(publish_status)", index_sql)


if __name__ == "__main__":
    unittest.main()
