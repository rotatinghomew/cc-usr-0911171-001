青年人才驿站床位协同与入住履约平台
测试：python3 -m unittest discover -s tests -v
构建：python3 -m compileall -q shelter_exchange tests
验收：python3 -m shelter_exchange --database /tmp/shelter_exchange.sqlite3 run --fixture fixtures/acceptance.json --output /tmp/shelter_exchange-output.json
单测：python3 -m unittest tests.test_domain -v
