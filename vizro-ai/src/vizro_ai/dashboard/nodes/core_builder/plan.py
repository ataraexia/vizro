"""Module containing the planner functionality."""

from typing import Dict, List, Literal, Union

import vizro.models as vm
from langchain_openai import ChatOpenAI
try:
    from pydantic.v1 import BaseModel, Field
except ImportError:  # pragma: no cov
    from pydantic import BaseModel, Field
from pydantic.v1 import Field, create_model, validator
from vizro.managers import model_manager
from vizro.tables import dash_ag_grid
from vizro.models import VizroBaseModel

from .model import get_model

component_type = Literal["AgGrid", "Card", "Graph"]
control_type = Literal["Filter"]


# def create_proxy_model(original_model: VizroBaseModel) -> BaseModel:
#     """
#     Create a new Pydantic model that contains the same fields and docstring as the original model,
#     but without any methods.

#     Args:
#         original_model (VizroBaseModel): The original Vizro model to copy fields and docstring from.

#     Returns:
#         BaseModel: A new Pydantic model with the same fields and docstring as the original model.
#     """
#     # Create the new model dynamically
#     proxy_model = create_model(
#         f'{original_model.__name__}Proxy',
#         **{field: (original_model.__annotations__[field], getattr(original_model, field, ...))
#            for field in original_model.__annotations__}
#     )
#     # Set the original docstring
#     proxy_model.__doc__ = original_model.__doc__
    
#     return proxy_model

class CardProxyModel(BaseModel):
    type: Literal["card"] = "card"
    text: str = Field(
        ..., description="Markdown string to create card title/text that should adhere to the CommonMark Spec."
    )
    href: str = Field(
        "",
        description="URL (relative or absolute) to navigate to. If not provided the Card serves as a text card only.",
    )

# CardProxyModel = create_proxy_model(vm.Card)


class Component(BaseModel):
    component_name: component_type
    component_description: str = Field(
        ...,
        description="Description of the component. Include everything that relates to this component. If possible do not paraphrase and keep the original description. Keep any links as original links.",
    )
    component_id: str = Field(
        pattern=r"^[a-z]+(_[a-z]+)?$", description="Small snake case description of this component"
    )
    data_frame: str = Field(
        ...,
        description="The name of the dataframe that this component will use. If the dataframe is not used, please specify that.",
    )

    def create(self, model, df_metadata):
        if self.component_name == "Graph":
            return vm.Graph()
        elif self.component_name == "AgGrid":
            return vm.AgGrid(id=self.component_id, figure=dash_ag_grid(data_frame=self.data_frame))
        elif self.component_name == "Card":
            return get_model(query=self.component_description, model=model, result_model=CardProxyModel, df_metadata=df_metadata)


class Components(BaseModel):
    components: List[Component]


def create_filter_proxy(df_cols, df_sample, available_components):
    def validate_targets(v):
        if v not in available_components:
            raise ValueError(f"targets must be one of {available_components}")
        return v
    
    def validate_column(v):
        if v not in df_cols:
            raise ValueError(f"column must be one of {df_cols}")

    # TODO: properly check this - e.g. what is the best way to ideally dynamically include the available components
    # even in the schema
    return create_model(
        "FilterProxy",
        column=(str, Field(..., description="The target column of the filter.")),
        targets=(
            List[str],
            Field([], description="The targets of the filter. Listen carefully to the instructions here."),
        ),
        __validators__={
            "validator1": validator("targets", pre=True, each_item=True, allow_reuse=True)(validate_targets),
            "validator2": validator("column", allow_reuse=True)(validate_column),
        },
        __base__=vm.Filter,
    )


class FilterProxyModel(BaseModel):
    type: Literal["filter"] = "filter"
    column: str = Field(..., description="Column of DataFrame to filter.")
    targets: List[str] = Field(
        [],
        description="Target component to be affected by filter. "
        "If none are given then target all components on the page that use `column`.",
    )
    selector: Literal["Checklist", "DatePicker", "Dropdown", "RadioItems", "RangeSlider", "Slider"] = None


class Control(BaseModel):
    control_name: control_type
    control_description: str = Field(
        ..., description="Description of the filter. Include everything that seems to relate to this filter."
    )
    data_frame: str = Field(
        ...,
        description="The name of the dataframe that this component will use. If the dataframe is not used, please specify that.",
    )

    # TODO: there is definitely room for dynamic model creation, e.g. with literals for targets
    def create(self, model, available_components, df_metadata):
        filter_prompt = (
            f"Create a filter from the following instructions: {self.control_description}. Do not make up "
            f"things that are optional and DO NOT configure actions, action triggers or action chains. If no options are specified, leave them out."
        )
        df_schema, df_sample = df_metadata[self.data_frame]["df_schema"], df_metadata[self.data_frame]["df_sample"]
        df_cols = list(df_schema.keys())
        # proxy = get_model(filter_prompt, model, result_model=create_filter_proxy(df_cols=df_cols, df_sample=df_sample, available_components=available_components), df_metadata=df_metadata)
        proxy = get_model(filter_prompt, model, result_model=FilterProxyModel, df_metadata=df_metadata)

        print(proxy.dict())
        actual = vm.Filter.parse_obj(
            proxy.dict(exclude={"selector": {"id": True, "actions": True}, "id": True, "type": True})
        )
        # del model_manager._ModelManager__models[proxy.id]  # TODO: This is very wrong and needs to change
        return actual


class Controls(BaseModel):
    controls: List[Control]


class PagePlanner(BaseModel):
    title: str = Field(
        ...,
        description="Title of the page. If no description is provided, make a short and concise title from the components.",
    )
    components: Components  # List[Component]#
    controls: Controls  # Optional[List[FilterPlanner]]#List[Control]#


class DashboardPlanner(BaseModel):
    title: str = Field(
        ...,
        description="Title of the dashboard. If no description is provided, make a short and concise title from the content of the pages.",
    )
    pages: List[PagePlanner]


def get_dashboard_plan(
        query: str, 
        model: Union[ChatOpenAI], 
        df_metadata: Dict[str, Dict[str, str]],
        ) -> DashboardPlanner:
    return get_model(query=query, model=model, result_model=DashboardPlanner, df_metadata=df_metadata)


def print_dashboard_plan(dashboard_plan):
    for i, page in enumerate(dashboard_plan.pages):
        for j in page.components.components:
            print("--> " + repr(j))
        for j in page.controls.controls:
            print("--> " + repr(j))
        print("\n")
