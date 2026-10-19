.PHONY: onboard fresh extract map eval eval-offline build health report demo-edit
onboard:        ## full pipeline, timed
	./run_onboarding.sh
fresh:          ## brand-new onboarding (clears warehouse + state)
	./run_onboarding.sh --fresh
extract:
	python3 -m extract.extract
map:
	python3 -m ai.coa_mapper
eval:
	python3 -m ai.eval_coa_mapper
eval-offline:
	python3 -m ai.eval_coa_mapper --offline
build:          ## loads .env so dbt picks the mapping seed for SOURCE_MODE
	[ -f .env ] && set -a && . ./.env && set +a; cd dbt && dbt build --profiles-dir .
health:
	python3 -m health.health_report
report:         ## reports/onboarding_report.html, one page for a founder
	python3 -m health.onboarding_report
demo-edit:      ## sample mode: back-dated edit outside the lookback window -> reconciliation fails
	python3 -m extract.extract --mode sample --simulate-edit old && cd dbt && SOURCE_MODE=sample dbt build --profiles-dir . --quiet; cd .. && python3 -m health.health_report
