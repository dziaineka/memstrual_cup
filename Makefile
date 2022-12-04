NAME   := skaborik/memstrual_cup
TAG    := $$(git describe --tags --abbrev=0)
IMG    := ${NAME}:${TAG}

build:
	@docker build -t ${IMG} .

push:
	@docker push ${IMG}
