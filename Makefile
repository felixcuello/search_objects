all:
	@echo ""
	@echo "========================================================================== "
	@echo "   Search Objects "
	@echo "========================================================================== "
	@echo ""
	@echo " make build                     # Build the containers"
	@echo " make shell                     # Enter the shell on the main container"
	@echo " make run                       # Run the app [foreground]"
	@echo " make db-upgrade                # Apply Alembic migrations"
	@echo " make db-migrate                # Autogenerate a migration (MSG='...')"
	@echo " make db-ping                   # SELECT 1 against MySQL"
	@echo ""

build:
	@docker compose build

shell:
	@docker compose run --service-ports --rm web bash

run:
	@docker compose run --service-ports --rm web

stop:
	@docker compose stop

db-upgrade:
	@docker compose run --rm web flask db upgrade

db-migrate:
	@docker compose run --rm web flask db migrate -m "$(MSG)"

db-ping:
	@docker compose run --rm web flask db-ping
