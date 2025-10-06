# FlexibleProductionTooling_IT2F

## test/postgres-to-mqtt

1. Run this querry to create the table:

```
CREATE TABLE assembly_instructions (
    id SERIAL PRIMARY KEY,
    product_code VARCHAR(50),
    step_number INT,
    instruction TEXT
); 
```

2. Next, run this querry to create the trigger for insert into the table:

```
CREATE OR REPLACE FUNCTION notify_new_instruction()
RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('new_instruction', row_to_json(NEW)::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS instruction_insert ON assembly_instructions;

CREATE TRIGGER instruction_insert
AFTER INSERT ON assembly_instructions
FOR EACH ROW
EXECUTE FUNCTION notify_new_instruction();
```
