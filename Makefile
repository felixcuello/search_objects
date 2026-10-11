all:
	@echo ""
	@echo "========================================================================== "
	@echo "   Search Objects "
	@echo "========================================================================== "
	@echo ""
	@echo " make build                     # Build the containers"
	@echo " make shell                     # Enter the shell on the main container"
	@echo " make run                       # Run the app [foreground]"
	@echo ""

build:
	@docker compose build

shell:
	@docker compose run web bash

run:
	@docker compose run web
