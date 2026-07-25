AUDIT ();

SELECT @columns, count() AS duplicate_count
FROM __ref("@model")
GROUP BY @columns
HAVING count() > 1
