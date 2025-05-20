echo "ruff"
ruff check
echo "mypy"
mypy dhcw_nhs_wales_inthub
echo "bandint"
bandit -r dhcw_nhs_wales_inthub
