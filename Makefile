all:
	@echo ""
	@echo "========================================================================== "
	@echo "   Search Objects "
	@echo "========================================================================== "
	@echo ""
	@echo " make build                     # Build the containers"
	@echo " make shell                     # Enter the shell on the main container"
	@echo " make run                       # Run the app [foreground]"
	@echo " make db-drop                   # Drop the database [destroys all data]"
	@echo " make db-create                 # Create the (empty) database"
	@echo " make db-migrate                # Apply pending migrations (rails db:migrate)"
	@echo " make db-generate               # Autogenerate a migration (MSG='...')"
	@echo " make db-ping                   # SELECT 1 against MySQL"
	@echo " make db-seed                   # Seed the database"
	@echo ""

build:
	@docker compose build

shell:
	@docker compose run --service-ports --rm web bash

run:
	@docker compose run --service-ports --rm web

stop:
	@docker compose stop

db-drop:
	@docker compose run -T db sh -c 'mysql -uroot -p"$$MYSQL_ROOT_PASSWORD" -e "DROP DATABASE IF EXISTS $$MYSQL_DATABASE"'

db-create:
	@docker compose run -T db sh -c 'mysql -uroot -p"$$MYSQL_ROOT_PASSWORD" -e "CREATE DATABASE IF NOT EXISTS $$MYSQL_DATABASE CHARACTER SET utf8mb4"'

db-migrate:
	@docker compose run --rm web flask db upgrade

db-generate:
	@docker compose run --rm web flask db migrate -m "$(MSG)"

db-ping:
	@docker compose run --rm web flask db-ping

db-seed:
	@docker compose run --rm web flask seed
