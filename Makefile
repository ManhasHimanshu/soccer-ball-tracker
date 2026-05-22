REGION=us-east-1
ENV=dev

validate-storage:
	aws cloudformation validate-template \
		--template-body file://infrastructure/storage.yaml

deploy-storage:
	aws cloudformation deploy \
		--template-file infrastructure/storage.yaml \
		--stack-name sbt-storage-$(ENV) \
		--parameter-overrides Environment=$(ENV) \
		--region $(REGION) \
		--capabilities CAPABILITY_NAMED_IAM

outputs-storage:
	aws cloudformation describe-stacks \
		--stack-name sbt-storage-$(ENV) \
		--region $(REGION) \
		--query 'Stacks[0].Outputs' \
		--output table

delete-storage:
	aws cloudformation delete-stack \
		--stack-name sbt-storage-$(ENV) \
		--region $(REGION)